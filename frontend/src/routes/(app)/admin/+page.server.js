import { error, redirect } from '@sveltejs/kit';
import { apiRequest } from '$lib/api-helpers.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ locals, cookies }) {
  const org = locals.org;
  if (!org) throw redirect(302, '/login');
  // Admin-only view. Non-admins are bounced to their normal home.
  if (locals.profile?.role !== 'ADMIN') throw redirect(302, '/');

  try {
    const data = await apiRequest('/dashboard/admin/', {}, { cookies, org });
    return {
      overview: data.overview || {},
      statusBreakdown: data.status_breakdown || [],
      followupHealth: data.followup_health || {},
      userMetrics: data.user_metrics || [],
      leadActivity: data.lead_activity || []
    };
  } catch (err) {
    console.error('Admin dashboard load error:', err);
    throw error(500, 'Failed to load admin dashboard');
  }
}
