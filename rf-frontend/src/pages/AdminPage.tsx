import React, { useCallback, useEffect, useState } from 'react';
import { HardDrive, ShieldCheck, Terminal, UserPlus, Users } from 'lucide-react';
import { STATUS } from '../design-system/tokens';
import { useTheme } from '../hooks/useTheme';
import { rf } from '../services/rasterforge';
import type { AdminStats } from '../types/rasterforge';
import type { AuthUser } from '../types';
import { StatusPill } from '../components/rf/StatusPill';
import { formatBytes, formatInt, formatRelative } from '../components/rf/format';
import {
  Button,
  Card,
  Field,
  KeyValue,
  Notice,
  PanelTitle,
  Pill,
  SectionLabel,
  Select,
  Spinner,
  TextInput,
} from '../components/rf/ui';

/* ============================================================================
 * AdminPage — users, storage, failures, and the resolved GDAL environment.
 *
 * The GDAL panel matters more than it looks: "tiling fails on this machine"
 * is almost always a discovery problem, and this shows exactly which install
 * and which gdal2tiles invocation the server settled on.
 * ========================================================================== */

const AdminPage: React.FC = () => {
  const { C } = useTheme();

  const [stats, setStats] = useState<AdminStats | null>(null);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('user');
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, u] = await Promise.all([rf.adminStats(), rf.adminUsers()]);
      setStats(s);
      setUsers(u);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load admin data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const createUser = useCallback(async () => {
    if (!newUsername || !newPassword) return;
    setCreating(true);
    try {
      await rf.createUser({ username: newUsername, password: newPassword, role: newRole });
      setNewUsername('');
      setNewPassword('');
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not create the user.');
    } finally {
      setCreating(false);
    }
  }, [newUsername, newPassword, newRole, load]);

  const toggleActive = useCallback(
    async (user: AuthUser) => {
      try {
        await rf.updateUser(Number(user.id), { is_active: !user.is_active });
        await load();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not update the user.');
      }
    },
    [load],
  );

  const td: React.CSSProperties = {
    fontSize: 12,
    color: C.t2,
    padding: '10px 12px',
    borderTop: `1px solid ${C.b}`,
  };

  if (loading) {
    return (
      <div className="rf-page" style={{ background: C.main }}>
        <div className="rf-container" style={{ display: 'flex', gap: 8, alignItems: 'center', color: C.t3 }}>
          <Spinner size={14} /> Loading…
        </div>
      </div>
    );
  }

  return (
    <div className="rf-page" style={{ background: C.main }}>
      <div className="rf-container">
        <h1
          style={{
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: '-0.02em',
            color: C.t1,
            marginBottom: 24,
          }}
        >
          Admin
        </h1>

        {error && (
          <div style={{ marginBottom: 16 }}>
            <Notice C={C} tone="error" title="Admin data unavailable">
              {error}
            </Notice>
          </div>
        )}

        {stats && (
          <>
            {/* GDAL environment */}
            <div style={{ marginBottom: 16 }}>
              <Card C={C}>
                <PanelTitle
                  C={C}
                  icon={Terminal}
                  right={
                    <Pill C={C} tone={stats.gdal.can_tile === 'yes' ? 'accent' : 'default'}>
                      {stats.gdal.can_tile === 'yes' ? 'Tiling available' : 'Tiling unavailable'}
                    </Pill>
                  }
                >
                  GDAL environment
                </PanelTitle>

                {stats.gdal.can_tile !== 'yes' && (
                  <div style={{ marginBottom: 16 }}>
                    <Notice C={C} tone="error" title="This server cannot generate tiles">
                      No GDAL install with <code>gdal2tiles</code> was found. On Windows, install
                      QGIS (OSGeo4W alone does not ship it) or set <code>GDAL_ROOT</code>.
                    </Notice>
                  </div>
                )}

                <div style={{ display: 'grid', gap: 0 }}>
                  {Object.entries(stats.gdal).map(([key, value]) => (
                    <KeyValue
                      key={key}
                      C={C}
                      label={key}
                      value={
                        <span
                          style={{
                            color: String(value ?? '').includes('NOT FOUND') ? STATUS.red : C.t1,
                            fontSize: 11,
                          }}
                        >
                          {value ?? '—'}
                        </span>
                      }
                      mono
                    />
                  ))}
                </div>
              </Card>
            </div>

            {/* Storage + counts */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                gap: 16,
                marginBottom: 16,
              }}
            >
              <Card C={C}>
                <PanelTitle C={C} icon={HardDrive}>
                  Storage
                </PanelTitle>
                <KeyValue C={C} label="Root" value={<span style={{ fontSize: 11 }}>{stats.storage.root}</span>} mono />
                <KeyValue C={C} label="Used by datasets" value={formatBytes(stats.storage.used_bytes)} />
                <KeyValue C={C} label="Free on disk" value={formatBytes(stats.storage.free_bytes)} />
                <div style={{ marginTop: 16 }}>
                  <SectionLabel C={C}>Largest datasets</SectionLabel>
                  {stats.storage.by_dataset.slice(0, 6).map((d) => (
                    <div
                      key={d.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '6px 0',
                        fontSize: 12,
                      }}
                    >
                      <span
                        style={{
                          flex: 1,
                          color: C.t1,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {d.display_name}
                      </span>
                      <span style={{ color: C.t3 }}>{formatBytes(d.size_bytes)}</span>
                    </div>
                  ))}
                </div>
              </Card>

              <Card C={C}>
                <PanelTitle C={C} icon={ShieldCheck}>
                  System
                </PanelTitle>
                <KeyValue C={C} label="Datasets" value={formatInt(stats.datasets.total)} />
                <KeyValue C={C} label="Published" value={formatInt(stats.datasets.published)} />
                <KeyValue C={C} label="Jobs total" value={formatInt(stats.jobs.total)} />
                <KeyValue
                  C={C}
                  label="Jobs running"
                  value={`${stats.jobs.active} active, ${stats.jobs.pending} queued (max ${stats.jobs.max_concurrent})`}
                />
                <KeyValue C={C} label="Jobs failed" value={formatInt(stats.jobs.failed)} />
                <div style={{ marginTop: 16 }}>
                  <SectionLabel C={C}>Limits</SectionLabel>
                  <KeyValue C={C} label="Max upload" value={`${stats.limits.max_upload_mb} MB`} />
                  <KeyValue C={C} label="Max pixels" value={formatInt(stats.limits.max_raster_pixels)} />
                  <KeyValue C={C} label="Min free disk" value={`${stats.limits.min_free_disk_gb} GB`} />
                  <KeyValue C={C} label="Job timeout" value={`${stats.limits.job_timeout_minutes} min`} />
                </div>
              </Card>
            </div>

            {/* Failed jobs */}
            {stats.failed_jobs.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <Card C={C} padding={16}>
                  <PanelTitle C={C}>Recent failures</PanelTitle>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 600 }}>
                      <tbody>
                        {stats.failed_jobs.map((j) => (
                          <tr key={j.id}>
                            <td style={{ ...td, color: C.t1, fontWeight: 600 }}>
                              {j.dataset_name ?? j.dataset_id}
                            </td>
                            <td style={td}>
                              <Pill C={C}>{j.error_code ?? 'unknown'}</Pill>
                            </td>
                            <td style={{ ...td, maxWidth: 380 }}>{j.error_message}</td>
                            <td style={{ ...td, whiteSpace: 'nowrap' }}>
                              {formatRelative(j.finished_at ?? j.created_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>
            )}
          </>
        )}

        {/* Users */}
        <Card C={C} padding={16}>
          <PanelTitle C={C} icon={Users}>
            Users
          </PanelTitle>

          <div style={{ overflowX: 'auto', marginBottom: 24 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 560 }}>
              <tbody>
                {users.map((u) => (
                  <tr key={String(u.id)}>
                    <td style={{ ...td, color: C.t1, fontWeight: 600 }}>{u.username}</td>
                    <td style={td}>{u.email ?? '—'}</td>
                    <td style={td}>
                      <Pill C={C} tone={u.role === 'admin' ? 'accent' : 'default'} uppercase>
                        {u.role}
                      </Pill>
                    </td>
                    <td style={td}>
                      <StatusPill C={C} status={u.is_active ? 'ready' : 'cancelled'} size="sm" />
                    </td>
                    <td style={{ ...td, textAlign: 'right' }}>
                      <Button C={C} variant="ghost" onClick={() => void toggleActive(u)}>
                        {u.is_active ? 'Deactivate' : 'Activate'}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <SectionLabel C={C}>Add a user</SectionLabel>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 16,
              alignItems: 'end',
            }}
          >
            <Field C={C} label="Username" htmlFor="rf-new-username">
              <TextInput id="rf-new-username" C={C} value={newUsername} onChange={setNewUsername} />
            </Field>
            <Field C={C} label="Password" htmlFor="rf-new-password">
              <TextInput
                id="rf-new-password"
                C={C}
                type="password"
                value={newPassword}
                onChange={setNewPassword}
              />
            </Field>
            <Field C={C} label="Role" htmlFor="rf-new-role">
              <Select
                id="rf-new-role"
                C={C}
                value={newRole}
                onChange={setNewRole}
                options={[
                  { value: 'user', label: 'User' },
                  { value: 'admin', label: 'Admin' },
                ]}
              />
            </Field>
            <div style={{ marginBottom: 16 }}>
              <Button
                C={C}
                variant="primary"
                icon={UserPlus}
                onClick={createUser}
                disabled={creating || !newUsername || !newPassword}
              >
                Create user
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default AdminPage;
