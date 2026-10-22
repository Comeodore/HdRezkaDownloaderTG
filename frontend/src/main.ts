import './app.css';
import { mount } from 'svelte';
import App from './App.svelte';
import { initTelegram } from './lib/telegram';

initTelegram();

export default mount(App, { target: document.getElementById('app')! });
