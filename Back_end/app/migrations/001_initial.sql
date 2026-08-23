-- ============================================================
-- Lyraa Agent — Multi-Tenant Schema
-- Run this in: Supabase → SQL Editor
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Tenants ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT NOT NULL,
  slug          TEXT UNIQUE NOT NULL,       -- used as Pinecone namespace: tenant_<slug>
  supabase_uid  TEXT UNIQUE NOT NULL,       -- owner's Supabase auth UID
  email         TEXT NOT NULL,
  created_at    TIMESTAMPTZ DEFAULT now(),
  is_active     BOOLEAN DEFAULT TRUE
);

-- ── Agent configuration per tenant ──────────────────────────
CREATE TABLE IF NOT EXISTS agent_configs (
  tenant_id     UUID REFERENCES tenants(id) ON DELETE CASCADE PRIMARY KEY,
  agent_name    TEXT DEFAULT 'Lyraa',
  system_prompt TEXT,
  greeting_msg  TEXT DEFAULT 'Hi! How can I help you today?',
  slack_channel TEXT,
  avatar_url    TEXT
);

-- ── API keys for widget/integrations ────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id     UUID REFERENCES tenants(id) ON DELETE CASCADE,
  key_hash      TEXT NOT NULL,              -- bcrypt hash of the full key
  key_prefix    TEXT NOT NULL,              -- e.g. "lyr_abc123" — shown to user
  label         TEXT,
  created_at    TIMESTAMPTZ DEFAULT now(),
  last_used_at  TIMESTAMPTZ,
  is_active     BOOLEAN DEFAULT TRUE
);

-- ── Usage logging for analytics ─────────────────────────────
CREATE TABLE IF NOT EXISTS usage_logs (
  id            BIGSERIAL PRIMARY KEY,
  tenant_id     UUID REFERENCES tenants(id) ON DELETE SET NULL,
  session_id    TEXT,
  intent        TEXT,
  created_at    TIMESTAMPTZ DEFAULT now(),
  response_ms   INTEGER
);

-- ── Subscriptions (placeholder — no Stripe yet) ─────────────
CREATE TABLE IF NOT EXISTS subscriptions (
  tenant_id     UUID REFERENCES tenants(id) ON DELETE CASCADE PRIMARY KEY,
  plan          TEXT DEFAULT 'free',        -- free | starter | pro | enterprise
  message_limit INTEGER DEFAULT 1000,
  messages_used INTEGER DEFAULT 0,
  period_start  TIMESTAMPTZ DEFAULT now(),
  period_end    TIMESTAMPTZ
);

-- ── Row Level Security (basic: tenants can only see their own rows) ──
ALTER TABLE tenants        ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_configs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys       ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_logs     ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions  ENABLE ROW LEVEL SECURITY;

-- NOTE: The FastAPI backend uses the service_role key which bypasses RLS.
-- RLS policies below are for direct Supabase client calls from the frontend (if ever needed).

CREATE POLICY "Tenants: owner access" ON tenants
  FOR ALL USING (supabase_uid = auth.uid()::text);

CREATE POLICY "Agent configs: owner access" ON agent_configs
  FOR ALL USING (
    tenant_id IN (SELECT id FROM tenants WHERE supabase_uid = auth.uid()::text)
  );

CREATE POLICY "API keys: owner access" ON api_keys
  FOR ALL USING (
    tenant_id IN (SELECT id FROM tenants WHERE supabase_uid = auth.uid()::text)
  );

CREATE POLICY "Usage logs: owner read" ON usage_logs
  FOR SELECT USING (
    tenant_id IN (SELECT id FROM tenants WHERE supabase_uid = auth.uid()::text)
  );

CREATE POLICY "Subscriptions: owner read" ON subscriptions
  FOR SELECT USING (
    tenant_id IN (SELECT id FROM tenants WHERE supabase_uid = auth.uid()::text)
  );

-- ── Helpful indexes ──────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_tenants_supabase_uid ON tenants(supabase_uid);
CREATE INDEX IF NOT EXISTS idx_api_keys_tenant      ON api_keys(tenant_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_tenant    ON usage_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_created   ON usage_logs(created_at);
