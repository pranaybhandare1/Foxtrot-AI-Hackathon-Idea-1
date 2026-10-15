/** Response types for the Ontology Manager API (apps/ontology-manager/api). */

export type OntologyProperty = { name: string; type: string; description: string; display_name?: string };
export type OntologyLink = { name: string; many: string; one: string; foreign_key: string; direction: "to_one" | "to_many"; target: string };
export type ObjectType = {
  name: string;
  description: string;
  primary_key: string;
  title: string | null;
  is_dataset: boolean;
  optional: boolean;
  group: string | null;
  icon: string;
  color: string;
  sources: string[];
  backing_dataset: string;
  updated_at: number | null;
  lineage: string[];
  count: number;
  properties: OntologyProperty[];
  links: OntologyLink[];
  actions: string[];
};
export type OntologyGroup = { name: string; display_name: string; description: string };
export type ActionParameter = { name: string; type: string; required: boolean; enum: string[] };
export type ActionType = { name: string; display_name: string; description: string; kind: "create" | "modify"; object_type: string; parameters: ActionParameter[] };
export type LinkTypeRow = { name: string; many: string; one: string; foreign_key: string; required: boolean };
export type OntologySchema = {
  name: string;
  version: number;
  groups: OntologyGroup[];
  object_types: ObjectType[];
  link_types: LinkTypeRow[];
  action_types: ActionType[];
};
export type MetricSpec = { label: string; fmt: string; better: "higher" | "lower" };

export type ObjectList = { total: number; rows: Record<string, unknown>[]; order_by: string; desc: boolean };
export type ObjectDetail = {
  type: string;
  primary_key: string;
  object: Record<string, unknown>;
  links: { link: string; target: string; cardinality: "one" | "many"; total: number; rows: Record<string, unknown>[] }[];
};

export type PropertyProfile = {
  null_pct: number | null;
  distinct: number | null;
  min: string | null;
  max: string | null;
  mean: string | null;
  std: string | null;
  q25: string | null;
  q50: string | null;
  q75: string | null;
  top?: { value: string; n: number }[];
};
export type Profile = { count: number; properties: Record<string, PropertyProfile> };

export type SqlResult = { columns: { name: string; type: string }[]; rows: Record<string, unknown>[]; truncated: boolean };

export type AgentTool = { name: string; kind: "read" | "write"; description: string; input_schema: Record<string, any> };

export type Workflow = {
  id: string;
  title: string;
  pillar: "glucose" | "recovery" | "connections" | "platform";
  status: "idea" | "prototype" | "live";
  trigger?: string;
  reads?: string[];
  writes?: string[];
  visuals?: string[];
  agent?: string;
  evidence?: string;
  steps?: string[];
  unknown: string[];
};
