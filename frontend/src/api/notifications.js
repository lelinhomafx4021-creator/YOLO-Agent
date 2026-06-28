import { get } from './client.js'

export function listNotificationJobs() {
  return get('/notifications/jobs')
}
