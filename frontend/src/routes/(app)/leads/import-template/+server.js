import { env } from '$env/dynamic/public';

const API_BASE_URL = `${env.PUBLIC_DJANGO_API_URL}/api`;
const XLSX_CONTENT_TYPE =
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/**
 * Stream the leads Excel import template from Django, forwarding the user's
 * JWT so the (authenticated) endpoint accepts the request. Same-origin so the
 * browser download just works.
 * @type {import('./$types').RequestHandler}
 */
export async function GET({ cookies }) {
  const token = cookies.get('jwt_access');
  const res = await fetch(`${API_BASE_URL}/leads/import/template.xlsx`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });
  if (!res.ok) {
    return new Response('Failed to generate template', { status: res.status });
  }
  const buf = await res.arrayBuffer();
  return new Response(buf, {
    headers: {
      'Content-Type': XLSX_CONTENT_TYPE,
      'Content-Disposition': 'attachment; filename="leads-import-template.xlsx"'
    }
  });
}
