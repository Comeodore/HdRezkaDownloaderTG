import './app.css';
import { mount } from 'svelte';
import App from './App.svelte';
import { initTelegram } from './lib/telegram';

initTelegram();

const app = mount(App, { target: document.getElementById('app')! });

export default app;
