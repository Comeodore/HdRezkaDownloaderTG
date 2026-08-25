import asyncio
import os
import time
from pathlib import Path
from typing import Callable

import aiohttp

from ..config import Settings
from ..logging_conf import get_logger
from .paths import episode_path, movie_path, series_dir, set_owner
from .progress import Job, JobReporter, JobStatus
from .quality import PREMIUM_QUALITIES, choose_quality, normalize_urls

logger = get_logger("engine")

IsCancelled = Callable[[], bool]


def select_seasons(all_keys: list, wanted: list[int]) -> list:
    chosen = set(wanted)
    ordered = sorted(all_keys, key=lambda value: int(value))
    return [key for key in ordered if not chosen or int(key) in chosen]


class DownloadEngine:
    def __init__(self, settings: Settings, http: aiohttp.ClientSession) -> None:
        self._settings = settings
        self._http = http

    async def run(self, api: object, job: Job, reporter: JobReporter, is_cancelled: IsCancelled) -> None:
        if job.is_series:
            await self._series(api, job, reporter, is_cancelled)
        else:
            await self._movie(api, job, reporter, is_cancelled)

    async def _movie(self, api: object, job: Job, reporter: JobReporter, is_cancelled: IsCancelled) -> None:
        stream = await asyncio.to_thread(api.getStream, translation=job.translator_id)
        urls, quality = await self._select(stream)
        if not urls:
            reporter.status(JobStatus.ERROR, "Не удалось получить ссылки на видео")
            return

        reporter.quality(quality)
        destination = movie_path(self._settings, api.name)
        result = await self._download_file(urls, destination, reporter, is_cancelled, label=api.name)

        if result == JobStatus.SUCCESS:
            reporter.status(JobStatus.SUCCESS)
        elif result == JobStatus.CANCELLED:
            reporter.status(JobStatus.CANCELLED)
        else:
            reporter.status(JobStatus.ERROR, job.error or "Ошибка загрузки")

    async def _series(self, api: object, job: Job, reporter: JobReporter, is_cancelled: IsCancelled) -> None:
        series_info = await asyncio.to_thread(lambda: api.seriesInfo)
        if not series_info or job.translator_id not in series_info:
            reporter.status(JobStatus.ERROR, "Нет информации о сериале")
            return

        translator_info = series_info[job.translator_id]
        seasons = translator_info.get("seasons", {})
        episodes_by_season = translator_info.get("episodes", {})
        if not seasons or not episodes_by_season:
            reporter.status(JobStatus.ERROR, "Нет информации о сезонах")
            return

        season_keys = select_seasons(list(seasons.keys()), job.seasons)
        total_episodes = sum(len(episodes_by_season.get(s, {})) for s in season_keys)
        reporter.episodes(0, total_episodes)

        root = series_dir(self._settings, api.name)
        root.mkdir(parents=True, exist_ok=True)
        set_owner(root, self._settings)

        done = 0
        for season_str in season_keys:
            if is_cancelled():
                reporter.status(JobStatus.CANCELLED)
                return
            season = int(season_str)
            for episode_str in sorted(episodes_by_season.get(season_str, {}).keys(), key=int):
                if is_cancelled():
                    reporter.status(JobStatus.CANCELLED)
                    return
                episode = int(episode_str)
                label = f"S{season:02d}E{episode:02d}"
                destination = episode_path(root, season, episode)

                if destination.exists() and destination.stat().st_size > 0:
                    done += 1
                    reporter.episodes(done, total_episodes)
                    continue

                try:
                    stream = await asyncio.to_thread(
                        api.getStream, season=season, episode=episode, translation=job.translator_id
                    )
                    urls, quality = await self._select(stream)
                    if not urls:
                        logger.warning("No urls for %s", label)
                        continue
                    reporter.quality(quality)
                    result = await self._download_file(urls, destination, reporter, is_cancelled, label=label)
                    if result == JobStatus.CANCELLED:
                        reporter.status(JobStatus.CANCELLED)
                        return
                    if result == JobStatus.SUCCESS:
                        done += 1
                        reporter.episodes(done, total_episodes)
                except Exception as exc:
                    logger.warning("Episode %s failed: %s", label, exc)

        if done == total_episodes and total_episodes > 0:
            reporter.status(JobStatus.SUCCESS)
        elif done > 0:
            reporter.status(JobStatus.PARTIAL)
        else:
            reporter.status(JobStatus.ERROR, "Не удалось скачать ни одного эпизода")

    async def _select(self, stream: object) -> tuple[list[str] | None, str | None]:
        videos = getattr(stream, "videos", None) or {}
        sizes: dict[str, int] = {}
        url_map: dict[str, list[str]] = {}
        for quality, raw in videos.items():
            if quality in PREMIUM_QUALITIES:
                continue
            urls = normalize_urls(raw)
            if not urls:
                continue
            size, ordered = await self._probe(urls)
            sizes[quality] = size
            url_map[quality] = ordered

        quality = choose_quality(sizes)
        if not quality:
            logger.warning("No usable quality among %s", {q: s for q, s in sizes.items()})
            return None, None
        logger.info("Selected %s (%.0f MB)", quality, sizes[quality] / 1024 / 1024)
        return url_map[quality], quality

    async def _probe(self, urls: list[str]) -> tuple[int, list[str]]:
        headers = {"User-Agent": self._settings.user_agent, "Range": "bytes=0-0"}
        for url in urls:
            try:
                async with self._http.get(url, headers=headers) as response:
                    total = self._range_total(response)
                    if total:
                        ordered = [url] + [other for other in urls if other != url]
                        return total, ordered
            except Exception as exc:
                logger.debug("Probe failed for mirror: %s", exc)
        return 0, urls

    @staticmethod
    def _range_total(response: aiohttp.ClientResponse) -> int:
        content_range = response.headers.get("content-range")
        if content_range and "/" in content_range:
            total = content_range.rsplit("/", 1)[-1]
            if total.isdigit():
                return int(total)
        if response.status == 200:
            length = response.headers.get("content-length")
            if length and length.isdigit():
                return int(length)
        return 0

    async def _download_file(
        self,
        urls: list[str],
        destination: Path,
        reporter: JobReporter,
        is_cancelled: IsCancelled,
        label: str = "",
    ) -> JobStatus:
        destination.parent.mkdir(parents=True, exist_ok=True)
        set_owner(destination.parent, self._settings)

        if destination.exists() and destination.stat().st_size > 0:
            return JobStatus.SUCCESS

        temp = destination.with_suffix(destination.suffix + ".part")
        current_size = temp.stat().st_size if temp.exists() else 0

        for attempt in range(self._settings.max_retries):
            if is_cancelled():
                return JobStatus.CANCELLED
            for index, url in enumerate(urls):
                if is_cancelled():
                    return JobStatus.CANCELLED
                logger.info("Download %s attempt %d url %d/%d", label, attempt + 1, index + 1, len(urls))
                status, current_size = await self._download_chunk(
                    url, temp, current_size, reporter, is_cancelled, label
                )
                if status == JobStatus.CANCELLED:
                    return JobStatus.CANCELLED
                if status == JobStatus.SUCCESS:
                    try:
                        os.replace(temp, destination)
                        set_owner(destination, self._settings)
                        return JobStatus.SUCCESS
                    except OSError as exc:
                        logger.error("Rename failed: %s", exc)
                        return JobStatus.ERROR
            if attempt < self._settings.max_retries - 1:
                await asyncio.sleep(self._settings.retry_delay)

        logger.error("Download failed after retries: %s", label)
        return JobStatus.ERROR

    async def _download_chunk(
        self,
        url: str,
        temp: Path,
        current_size: int,
        reporter: JobReporter,
        is_cancelled: IsCancelled,
        label: str,
    ) -> tuple[JobStatus, int]:
        downloaded = current_size
        headers = {"User-Agent": self._settings.user_agent}
        if current_size > 0:
            headers["Range"] = f"bytes={current_size}-"

        started = time.time()
        threshold = self._settings.chunk_size * 10
        last_reported = 0

        try:
            async with self._http.get(url, headers=headers) as response:
                if response.status not in (200, 206):
                    return JobStatus.ERROR, downloaded
                total = self._content_length(response, current_size)
                mode = "ab" if current_size > 0 else "wb"
                with open(temp, mode) as handle:
                    async for chunk in response.content.iter_chunked(self._settings.chunk_size):
                        if is_cancelled():
                            return JobStatus.CANCELLED, downloaded
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if downloaded - last_reported > threshold:
                            last_reported = downloaded
                            elapsed = time.time() - started
                            speed = (downloaded - current_size) / elapsed / 1024 / 1024 if elapsed > 0 else 0.0
                            reporter.progress(downloaded, total, round(speed, 1), current=label)
                return JobStatus.SUCCESS, downloaded
        except asyncio.TimeoutError:
            logger.warning("Timeout downloading %s", label)
            return JobStatus.ERROR, downloaded
        except Exception as exc:
            logger.warning("Chunk error %s: %s", label, exc)
            return JobStatus.ERROR, downloaded

    @staticmethod
    def _content_length(response: aiohttp.ClientResponse, current_size: int) -> int:
        if "content-length" not in response.headers:
            return 0
        if response.status == 206 and "content-range" in response.headers:
            parts = response.headers["content-range"].split("/")
            if len(parts) == 2 and parts[1].isdigit():
                return int(parts[1])
        return int(response.headers["content-length"]) + current_size
