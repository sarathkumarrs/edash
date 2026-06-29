/**
 * Module registry — which CRM modules a workspace can show.
 *
 * Keep these keys in sync with the backend registry at
 * `backend/common/modules.py`. The org's enabled list rides in the JWT
 * (`enabled_modules` claim) and is read in `hooks.server.js`.
 *
 * Always-on shell areas (Home `/`, `/profile`, `/settings`, `/users`, `/org`)
 * are intentionally NOT listed here — they are never gated.
 */

/** @typedef {{ key: string, label: string, prefixes: string[] }} ModuleDef */

/** @type {ModuleDef[]} */
export const MODULES = [
  { key: 'leads', label: 'Leads', prefixes: ['/leads'] },
  { key: 'contacts', label: 'Contacts', prefixes: ['/contacts'] },
  { key: 'accounts', label: 'Accounts', prefixes: ['/accounts'] },
  { key: 'deals', label: 'Deals', prefixes: ['/opportunities'] },
  { key: 'tickets', label: 'Tickets', prefixes: ['/tickets', '/solutions'] },
  { key: 'tasks', label: 'Tasks', prefixes: ['/tasks'] },
  { key: 'timesheet', label: 'Timesheet', prefixes: ['/timesheet'] },
  { key: 'goals', label: 'Goals', prefixes: ['/goals'] },
  { key: 'invoices', label: 'Invoices', prefixes: ['/invoices'] },
  { key: 'helpdesk', label: 'Help desk', prefixes: ['/support'] }
];

export const ALL_MODULE_KEYS = MODULES.map((m) => m.key);

/**
 * Whether a module is enabled. A missing/invalid list is treated as "all on"
 * so older sessions (JWTs minted before this feature) aren't broken.
 * @param {string[]|null|undefined} enabled
 * @param {string} key
 * @returns {boolean}
 */
export function isModuleEnabled(enabled, key) {
  if (!Array.isArray(enabled)) return true;
  return enabled.includes(key);
}

/**
 * Map a pathname to the module key that owns it, or null for always-on routes.
 * @param {string} pathname
 * @returns {string|null}
 */
export function moduleForPath(pathname) {
  for (const m of MODULES) {
    for (const prefix of m.prefixes) {
      if (pathname === prefix || pathname.startsWith(prefix + '/')) {
        return m.key;
      }
    }
  }
  return null;
}
