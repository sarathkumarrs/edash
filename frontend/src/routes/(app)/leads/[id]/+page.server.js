/**
 * Lead Detail Page - Server Load
 *
 * Django endpoint: GET /api/leads/<id>/
 * Response shape: { lead_obj, attachments, comments, users_mention, assigned_data,
 *                   users, users_excluding_team, source, status, teams, countries }
 * (see backend/leads/views/lead_views.py LeadDetailView.get_context_data)
 */

import { error, fail } from '@sveltejs/kit';
import { apiRequest } from '$lib/api-helpers.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ params, locals, cookies }) {
  const org = locals.org;
  if (!org) {
    throw error(401, 'Organization context required');
  }

  try {
    const response = await apiRequest(`/leads/${params.id}/`, {}, { cookies, org });

    if (response?.error) {
      throw error(404, response.errors || 'Lead not found');
    }

    // Django LeadDetailView returns the lead under `lead_obj` (see backend/leads/views/lead_views.py).
    const lead = response.lead_obj || response.lead || response;

    // Interaction timeline + admin-managed outcome options (best-effort: a
    // failure here shouldn't break the whole lead page).
    const [interactionsRes, outcomesRes] = await Promise.all([
      apiRequest(`/leads/${params.id}/interactions/`, {}, { cookies, org }).catch(() => ({
        interactions: []
      })),
      apiRequest(
        '/custom-fields/?target_model=LeadInteraction&active_only=true',
        {},
        { cookies, org }
      ).catch(() => ({ definitions: [] }))
    ]);
    const outcomeDef = (outcomesRes.definitions || []).find((d) => d.key === 'outcome');

    return {
      lead,
      comments: response.comments || [],
      attachments: response.attachments || [],
      tags: response.tags || lead?.tags || [],
      users: response.users || [],
      commentPermission: response.comment_permission || false,
      customFieldDefinitions: response.custom_field_definitions || [],
      customFieldValues: lead?.custom_fields || {},
      interactions: interactionsRes.interactions || [],
      outcomeOptions: outcomeDef?.options || []
    };
  } catch (err) {
    if (/** @type {any} */ (err)?.status) throw err;
    console.error('Failed to load lead detail:', err);
    throw error(500, 'Failed to load lead');
  }
}

/** @type {import('./$types').Actions} */
export const actions = {
  updateCustomFields: async ({ request, params, locals, cookies }) => {
    const form = await request.formData();
    const raw = form.get('custom_fields')?.toString() || '{}';
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return fail(400, { error: 'Malformed custom_fields payload' });
    }
    try {
      await apiRequest(
        `/leads/${params.id}/`,
        { method: 'PATCH', body: { custom_fields: parsed } },
        { cookies, org: locals.org }
      );
      return { success: true };
    } catch (err) {
      console.error('Update lead custom fields error:', err);
      return fail(400, {
        error: /** @type {any} */ (err)?.message || 'Failed to save custom fields'
      });
    }
  },

  logContact: async ({ request, params, locals, cookies }) => {
    const form = await request.formData();
    const notes = form.get('notes')?.toString().trim() || '';
    if (!notes) {
      return fail(400, { error: 'Notes are required.' });
    }
    const body = {
      interaction_type: form.get('interaction_type')?.toString() || 'call',
      outcome: form.get('outcome')?.toString() || '',
      notes,
      next_follow_up: form.get('next_follow_up')?.toString() || null
    };
    const occurredAt = form.get('occurred_at')?.toString();
    if (occurredAt) body.occurred_at = occurredAt;
    try {
      await apiRequest(
        `/leads/${params.id}/interactions/`,
        { method: 'POST', body },
        { cookies, org: locals.org }
      );
      return { success: true };
    } catch (err) {
      console.error('Log contact error:', err);
      return fail(400, {
        error: /** @type {any} */ (err)?.message || 'Failed to log contact'
      });
    }
  },

  deleteInteraction: async ({ request, locals, cookies }) => {
    const form = await request.formData();
    const id = form.get('id')?.toString();
    if (!id) return fail(400, { error: 'Missing interaction id' });
    try {
      await apiRequest(
        `/leads/interactions/${id}/`,
        { method: 'DELETE' },
        { cookies, org: locals.org }
      );
      return { success: true };
    } catch (err) {
      console.error('Delete interaction error:', err);
      return fail(400, {
        error: /** @type {any} */ (err)?.message || 'Failed to delete interaction'
      });
    }
  }
};
