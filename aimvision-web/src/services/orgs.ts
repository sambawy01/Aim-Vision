import { fetchJson } from './api';

/** Wire shape matches the backend's OrgOut DTO (snake_case). */
interface OrgWire {
  id: string;
  name: string;
  kind: string;
  tenant_id: string;
  federation_id: string | null;
}

export interface Org {
  id: string;
  name: string;
  kind: string;
  tenantId: string;
  federationId: string | null;
}

function toOrg(wire: OrgWire): Org {
  return {
    id: wire.id,
    name: wire.name,
    kind: wire.kind,
    tenantId: wire.tenant_id,
    federationId: wire.federation_id,
  };
}

export async function listOrgs(): Promise<Org[]> {
  const wire = await fetchJson<OrgWire[]>('/orgs');
  return wire.map(toOrg);
}
