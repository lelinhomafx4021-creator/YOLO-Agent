import { get, post, put } from './client.js'

export function getSettings() { return get('/settings') }
export function updateSettings(data) { return put('/settings', data) }
export function testConnection() { return post('/settings/test-connection') }
