import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useEditContext, useHistory, useLineage, useManagerSave, useManagerState, useOntology, type LineageNode } from "../api/client";
import type { ObjectType, OntologyProperty } from "../api/types";
import { Drawer } from "../components/Drawer";
import { Icons } from "../components/Icons";
import { TypeIcon } from "../components/TypeIcon";
import { Loader } from "../components/ui";

const label = (s: string) => s.replace(/([a-z0-9])([A-Z])/g, "$1 $2").replace(/_/g, " ");
const json = (v: unknown) => v === undefined ? "—" : JSON.stringify(v);
export function PageHeading({ eyebrow, title, description, children }: { eyebrow: string; title: string; description: string; children?: React.ReactNode }) {
  return <header className="workspace-heading"><div><div className="eyebrow">ONTOLOGY / {eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{children}</header>;
}

export function WorkspaceHome() {
  const { data: s } = useOntology();
  const { data: state } = useManagerState();
  const { data: history } = useHistory();
  if (!s) return null;
  const total = s.object_types.filter(t => !t.is_dataset).reduce((n, t) => n + t.count, 0);
  return <>
    <PageHeading eyebrow="OVERVIEW" title="Kaizen" description="Small steps. Better every day. Connect your health and habits, discover patterns, and learn what helps you improve.">
      <Link className="btn primary" to="/object-types">Browse object types <Icons.right /></Link>
    </PageHeading>
    <div className="workspace-notice"><span className="status-dot" /><b>Local ontology</b><span>t1d · version {s.version}</span><span className="notice-end">Changes persist on this machine</span></div>
    <div className="workspace-metrics">
      {[['Object types', s.object_types.length, '/object-types'], ['Link types', s.link_types.length, '/link-types'], ['Properties', s.object_types.reduce((n,t) => n+t.properties.length,0), '/properties'], ['Objects', total.toLocaleString(), '/object-types']].map(([name,value,to]) => <Link key={name} to={String(to)}><span>{name}</span><strong>{value}</strong><span className="metric-arrow">↗</span></Link>)}
    </div>
    <div className="workspace-section-title"><h2>Understand. Connect. Improve.</h2><span>Your foundation for continuous improvement</span></div>
    <div className="workspace-tools">
      {[
        { to: '/object-types', icon: <Icons.overview />, title: 'Ontology Manager', sub: 'Understand your starting point.', text: 'Inspect object types, relationships, backing data, and the actions that connect them.' },
        { to: '/lineage', icon: <Icons.explorer />, title: 'Data Lineage', sub: 'See how the pieces connect.', text: 'Trace source systems through processing layers into datasets and ontology objects.' },
        { to: '/properties', icon: <Icons.history />, title: 'Property Manager', sub: 'Make every detail meaningful.', text: 'Find properties across the ontology and edit their display names and descriptions.' },
      ].map(x => <Link className="workspace-tool" key={x.to} to={x.to}><div className="tool-icon">{x.icon}</div><h3>{x.title}</h3><b>{x.sub}</b><p>{x.text}</p><span className="tool-open">Open application <Icons.right /></span></Link>)}
    </div>
    <div className="workspace-bottom">
      <section className="workspace-panel"><div className="workspace-panel-head"><h2>Object types</h2><Link to="/object-types">View all {s.object_types.length} →</Link></div>
        <div className="resource-rows">{s.object_types.filter(t => !t.is_dataset).slice(0,6).map(t => <Link key={t.name} to={`/object-types/${t.name}`}><TypeIcon icon={t.icon} color={t.color} size={28}/><span><b>{label(t.name)}</b><small>{t.backing_dataset}</small></span><span className="resource-count">{t.count.toLocaleString()} objects</span><Icons.right /></Link>)}</div>
      </section>
      <section className="workspace-panel"><div className="workspace-panel-head"><h2>Your progress, recorded</h2><Link to="/history">View history →</Link></div>
        <div className="activity-summary"><strong>{state?.overrides ?? 0}</strong><span>property values overridden<br/><small>Source datasets stay unchanged</small></span></div>
        {history?.entries.length ? history.entries.slice(0,3).map(e => <div className="activity-row" key={e.id}><span className="activity-mark"/><div><b>{e.object_type}</b><p>{e.kind.replaceAll('.', ' · ')}</p><small>{new Date(e.created_at).toLocaleString()}</small></div></div>) : <div className="activity-empty"><Icons.history /><b>Every improvement starts somewhere</b><p>Saved metadata and object edits will appear here with their previous and new values.</p></div>}
        <div className="panel-foot"><Icons.quality /> Raw and transformed layers are read-only</div>
      </section>
    </div>
  </>;
}

export function MetadataEditor({ type, property, onClose }: { type: ObjectType; property?: OntologyProperty; onClose: () => void }) {
  const { data: state, error } = useManagerState();
  // Capture the revision with this draft. A concurrent save must produce a conflict, not overwrite it.
  const [revision, setRevision] = useState<string | null>(null);
  if (state && revision === null) setRevision(state.revision);
  const { data: schema } = useOntology();
  const [description, setDescription] = useState(property?.description ?? type.description);
  const [displayName, setDisplayName] = useState(property?.display_name ?? label(property?.name ?? ''));
  const [group, setGroup] = useState(type.group ?? '');
  const [color, setColor] = useState(type.color);
  const [title, setTitle] = useState(type.title ?? type.primary_key);
  const save = useManagerSave();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate({path: `/types/${type.name}${property ? `/properties/${property.name}` : ''}`, body: {revision, changes: property ? {display_name: displayName, description} : {description, group, color, title}}}, {onSuccess: onClose});
  };
  return <Drawer title={property ? 'Edit property' : 'Configure object type'} sub={`${type.name}${property ? ` / ${property.name}` : ''}`} onClose={onClose}>
    <form className="manager-form" onSubmit={submit}>
      <div className="form-note"><Icons.report /><div><b>Ontology definition</b><p>Saves to ontology/ontology.yaml. Backing datasets and their values are unchanged.</p></div></div>
      <label>API name<input className="text-input mono" readOnly value={property?.name ?? type.name}/></label>
      {property && <><label>Display name<input className="text-input" value={displayName} onChange={e => setDisplayName(e.target.value)}/></label><label>Base type<input className="text-input" readOnly value={property.type}/></label></>}
      <label>Description<textarea className="text-input" rows={5} value={description} onChange={e => setDescription(e.target.value)}/></label>
      {!property && <><label>Group<select className="select" value={group} onChange={e => setGroup(e.target.value)}>{schema?.groups.map(g => <option key={g.name} value={g.name}>{g.display_name}</option>)}</select></label><label>Title property<select className="select" value={title} onChange={e => setTitle(e.target.value)}>{type.properties.map(p => <option key={p.name}>{p.name}</option>)}</select></label><label>Object color<div className="row"><input aria-label="Object color" type="color" value={color} onChange={e => setColor(e.target.value)}/><span className="mono">{color}</span></div></label></>}
      {property && <p className="muted">API names, storage types, and keys are fixed to the backing schema. Changing them requires a data migration.</p>}
      {(save.error || error) && <div role="alert" className="error-box">{String(save.error ?? error)}</div>}
      <div className="form-actions"><button type="button" className="btn" onClick={onClose}>Cancel</button><button className="btn primary" disabled={!revision || save.isPending}>{save.isPending ? 'Saving…' : 'Save changes'}</button></div>
    </form>
  </Drawer>;
}

export function PropertiesPage() {
  const { data: schema } = useOntology();
  const [search, setSearch] = useState('');
  const [type, setType] = useState('');
  const [edit, setEdit] = useState<{type: ObjectType; property: OntologyProperty} | null>(null);
  const rows = (schema?.object_types ?? []).filter(t => !type || t.name === type).flatMap(t => t.properties.map(p => ({t,p}))).filter(({t,p}) => `${t.name} ${p.name} ${p.display_name} ${p.description}`.toLowerCase().includes(search.toLowerCase()));
  return <>
    <PageHeading eyebrow="RESOURCES" title="Property Manager" description="A shared catalog of the fields that give your ontology meaning."/>
    <div className="manager-toolbar"><div className="search-field"><Icons.search/><input aria-label="Search properties" placeholder="Search properties, descriptions, or object types…" value={search} onChange={e => setSearch(e.target.value)}/></div><select className="select" aria-label="Filter by object type" value={type} onChange={e => setType(e.target.value)}><option value="">All object types</option>{schema?.object_types.map(t => <option key={t.name}>{t.name}</option>)}</select><span className="muted">{rows.length} properties</span></div>
    <div className="glass om-table"><table><thead><tr><th>Property</th><th>API name</th><th>Object type</th><th>Base type</th><th>Description</th><th/></tr></thead><tbody>{rows.map(({t,p}) => <tr key={`${t.name}.${p.name}`} onClick={() => setEdit({type:t,property:p})}><td><b>{p.display_name || label(p.name)}</b>{p.name===t.primary_key && <span className="key-label">PK</span>}</td><td className="mono faint">{p.name}</td><td><span className="row"><TypeIcon icon={t.icon} color={t.color} size={20}/>{label(t.name)}</span></td><td><span className={`om-type-badge ${p.type}`}>{p.type}</span></td><td className="property-description">{p.description || '—'}</td><td><button className="btn small" aria-label={`Edit ${t.name}.${p.name}`}>Edit</button></td></tr>)}</tbody></table>{!rows.length && <div className="activity-empty">No properties match your filters.</div>}</div>
    {edit && <MetadataEditor {...edit} onClose={() => setEdit(null)}/>}
  </>;
}

export function RecordEditor({ type, pk, onClose }: { type: ObjectType; pk: string; onClose: () => void }) {
  const q = useEditContext(type.name, pk);
  const save = useManagerSave();
  const [draft, setDraft] = useState<Record<string,string>>({});
  const [nulls, setNulls] = useState<Record<string,boolean>>({});
  const [problem, setProblem] = useState('');
  const [review, setReview] = useState(false);
  const changes: Record<string,unknown> = {};
  for (const p of type.properties) {
    if (!(p.name in draft) && !(p.name in nulls)) continue;
    const raw = draft[p.name] ?? String(q.data?.object[p.name] ?? '');
    changes[p.name] = nulls[p.name] ? null : p.type === 'boolean' ? raw === 'true' : ['integer','double'].includes(p.type) ? (raw.trim() === '' ? NaN : Number(raw)) : raw;
  }
  const changed = Object.fromEntries(Object.entries(changes).filter(([k,v]) => v !== q.data?.object[k]));
  const submit = (restore = false) => {
    if (Object.values(changed).some(v => typeof v === 'number' && !Number.isFinite(v))) {setProblem('Enter a valid number, or select NULL.'); return;}
    const expected = restore ? q.data?.overrides : Object.fromEntries(Object.keys(changed).map(k => [k,q.data?.object[k]]));
    save.mutate({path:`/objects/${type.name}/${encodeURIComponent(pk)}${restore ? '/restore' : ''}`,body:restore ? {expected} : {changes:changed,expected}}, {onSuccess:onClose});
  };
  return <div className="record-editor"><div className="workspace-panel-head"><h3>Edit object values</h3><button className="btn small" onClick={onClose}>Cancel</button></div>
    <div className="form-note"><Icons.quality/><div><b>Separate object overrides</b><p>Edits are stored locally. Base datasets are unchanged. Derived metrics are not recalculated automatically.</p></div></div>
    <Loader query={q} height={200}>{d => <>
      {review ? <><h3>Review changes</h3><table className="edit-review"><thead><tr><th>Property</th><th>Before</th><th>After</th></tr></thead><tbody>{Object.entries(changed).map(([k,v]) => <tr key={k}><td>{k}</td><td>{json(d.object[k])}</td><td>{json(v)}</td></tr>)}</tbody></table></> : <div className="record-fields">{type.properties.map(p => <label key={p.name}><span>{p.display_name || label(p.name)} <code>{p.type}</code>{p.name in d.overrides && <span className="edited-tag">edited</span>}</span><div className="row">{d.protected.includes(p.name) ? <input className="text-input" readOnly value={String(d.object[p.name] ?? '')} title="Key properties are protected"/> : <>{p.type === 'boolean' ? <select className="select" aria-label={p.name} disabled={nulls[p.name] ?? d.object[p.name] === null} value={draft[p.name] ?? String(d.object[p.name] ?? 'false')} onChange={e => {setDraft({...draft,[p.name]:e.target.value});setReview(false);}}><option value="true">true</option><option value="false">false</option></select> : <input className="text-input" aria-label={p.name} disabled={nulls[p.name] ?? d.object[p.name] === null} value={draft[p.name] ?? String(d.object[p.name] ?? '')} onChange={e => {setDraft({...draft,[p.name]:e.target.value});setReview(false);}}/>}<label className="null-control"><input type="checkbox" checked={nulls[p.name] ?? d.object[p.name] === null} onChange={e => setNulls({...nulls,[p.name]:e.target.checked})}/> NULL</label></>}</div>{p.name in d.overrides && <small className="faint">Base: {json(d.base[p.name])}</small>}</label>)}</div>}
      {(save.error || problem) && <div role="alert" className="error-box">{problem || String(save.error)}</div>}
      <div className="form-actions">{Object.keys(d.overrides).length > 0 && <button className="btn" disabled={save.isPending} onClick={() => submit(true)}>Restore base values</button>}{review ? <><button className="btn" onClick={() => setReview(false)}>Back</button><button className="btn primary" disabled={save.isPending} onClick={() => submit()}>{save.isPending ? 'Saving…' : 'Save overrides'}</button></> : <button className="btn primary" disabled={!Object.keys(changed).length} onClick={() => {if(Object.values(changed).some(v => typeof v==='number' && !Number.isFinite(v))) setProblem('Enter valid numbers or select NULL.'); else {setProblem('');setReview(true);}}}>Review {Object.keys(changed).length || ''} changes</button>}</div>
    </>}</Loader>
  </div>;
}

const LAYERS = ['source','raw','transformed','clean','ontology'];
const LAYER_LABELS = ['Sources','Raw data','Transformed','Backing datasets','Ontology'];
export function LineagePage() {
  const q = useLineage();
  const { data: schema } = useOntology();
  const [focus, setFocus] = useState('Day');
  const [selected, setSelected] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const navigate = useNavigate();
  const graph = useMemo(() => {
    if (!q.data) return {nodes:[],edges:[],height:650};
    let ids = new Set(q.data.nodes.map(n => n.id));
    if (focus) {
      ids = new Set([`object/${focus}`]);
      let previous = -1;
      while (previous !== ids.size) {previous = ids.size; for (const e of q.data.edges) if (ids.has(e.target)) ids.add(e.source);}
    }
    const nodes = q.data.nodes.filter(n => ids.has(n.id));
    const position = (n: LineageNode) => n.layer === 'writeback' ? 'clean' : n.layer === 'edits' ? 'transformed' : n.layer;
    const counts = LAYERS.map(l => nodes.filter(n => position(n) === l).length);
    const height = Math.max(540,Math.max(...counts)*76+100);
    const placed = nodes.map(n => {
      const column = LAYERS.indexOf(position(n));
      const peers = nodes.filter(x => position(x) === position(n));
      return {...n,x:column*240+24,y:80+peers.indexOf(n)*76+(focus ? (4-peers.length)*38 : 0)};
    });
    return {nodes:placed,edges:q.data.edges.filter(e => ids.has(e.source)&&ids.has(e.target)),height};
  },[q.data,focus]);
  const active = graph.nodes.find(n => n.id === selected);
  return <>
    <PageHeading eyebrow="DATA INTEGRATION" title="Data Lineage" description="Trace the path from source systems to the objects your applications use."/>
    <div className="manager-toolbar"><span className="row"><Icons.explorer/> Upstream dependencies</span><select className="select" aria-label="Lineage object type" value={focus} onChange={e => {setFocus(e.target.value);setSelected(null);}}><option value="">All object types</option>{schema?.object_types.map(t => <option key={t.name}>{t.name}</option>)}</select><span className="toolbar-spacer"/><button className="btn" aria-label="Zoom out" onClick={() => setZoom(Math.max(.5,zoom-.1))}>−</button><span>{Math.round(zoom*100)}%</span><button className="btn" aria-label="Zoom in" onClick={() => setZoom(Math.min(1.5,zoom+.1))}>+</button><button className="btn" onClick={() => setZoom(1)}>Reset view</button></div>
    <Loader query={q} height={450}>{data => <div className="lineage-workspace"><div className="lineage-canvas"><div style={{width:1220*zoom,height:graph.height*zoom,position:'relative'}}><div style={{width:1220,height:graph.height,transform:`scale(${zoom})`,transformOrigin:'top left',position:'absolute'}}>
      <div className="lineage-columns">{LAYER_LABELS.map((l,i) => <span key={l}>{l}<small>{i===1 || i===2 ? 'PROTECTED' : i===4 ? 'APPLICATION LAYER' : ''}</small></span>)}</div>
      <svg className="lineage-edges" width={1220} height={graph.height} aria-hidden><defs><marker id="lineage-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="currentColor"/></marker></defs>{graph.edges.map((e,i) => {const a=graph.nodes.find(n=>n.id===e.source)!,b=graph.nodes.find(n=>n.id===e.target)!; const x=a.x+198,y=a.y+25;return <path key={i} d={`M${x},${y} C${x+28},${y} ${b.x-28},${b.y+25} ${b.x},${b.y+25}`} className={e.kind==='override'?'override-edge':''} markerEnd="url(#lineage-arrow)"/>;})}</svg>
      {graph.nodes.map(n => <button key={n.id} className={`lineage-resource ${n.layer} ${n.id===selected?'selected':''}`} style={{left:n.x,top:n.y}} onClick={() => setSelected(n.id)}><span className="lineage-resource-icon">{n.layer==='ontology'?<Icons.overview/>:n.layer==='edits'?<Icons.history/>:<Icons.report/>}</span><span><b>{n.label}</b><small>{n.layer==='ontology'?'Object type':n.layer==='edits'?'Local SQLite overrides':n.available?'Available locally':'Declared · external'}</small></span></button>)}
    </div></div></div><aside className="lineage-inspector"><div className="eyebrow">RESOURCE INSPECTOR</div>{active ? <><div className="inspector-icon"><Icons.report/></div><h3>{active.label}</h3><span className="chip">{active.layer}</span><p>{active.available?'This resource is available in the local workspace.':'This upstream resource is declared in source mappings. Its data is not shipped with this repository.'}</p>{active.path&&<code>{active.path}</code>}{active.object_type&&<button className="btn primary" onClick={() => navigate(`/object-types/${active.object_type}`)}>Open object type <Icons.right/></button>}</> : <><div className="inspector-icon"><Icons.explorer/></div><h3>Follow the data</h3><p>Select a resource to inspect its storage layer and availability.</p></>}<div className="inspector-foot"><Icons.quality/><p>Raw and transformed layers are protected. Object edits apply after the backing dataset.</p></div></aside><div className="lineage-caption">{data.basis}</div></div>}</Loader>
  </>;
}

export function HistoryPage() {
  const q=useHistory();
  const [search,setSearch]=useState('');
  return <><PageHeading eyebrow="OPERATIONS" title="Change history" description="A persistent record of metadata changes, value overrides, and restores."/><div className="manager-toolbar"><div className="search-field"><Icons.search/><input aria-label="Search changes" placeholder="Filter by object type or change…" value={search} onChange={e=>setSearch(e.target.value)}/></div><span className="muted">Most recent 200 changes · local workspace</span></div><Loader query={q} height={300}>{d=><div className="history-list">{d.entries.filter(e=>`${e.kind} ${e.object_type} ${e.primary_key}`.toLowerCase().includes(search.toLowerCase())).map(e=><article className="history-entry" key={e.id}><div className="history-entry-head"><span className="chip">{e.kind}</span><b>{e.object_type}</b><code>{e.primary_key}</code><time>{new Date(e.created_at).toLocaleString()}</time></div><table className="edit-review"><thead><tr><th>Property</th><th>Previous value</th><th>Saved value</th></tr></thead><tbody>{Object.keys(e.after).map(k=><tr key={k}><td>{k}</td><td>{json(e.before[k])}</td><td>{json(e.after[k])}</td></tr>)}</tbody></table></article>)}{!d.entries.length&&<div className="workspace-panel activity-empty"><Icons.history/><h3>No changes yet</h3><p>Edit an object type, property, or object value to begin a traceable history.</p><Link className="btn" to="/properties">Open Property Manager</Link></div>}</div>}</Loader></>;
}
