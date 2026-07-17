-- AI Trend Radar — schema (idempotent)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS repositories (
  id              BIGSERIAL PRIMARY KEY,
  github_id       BIGINT NOT NULL UNIQUE,
  full_name       TEXT   NOT NULL,
  owner           TEXT   NOT NULL,
  name            TEXT   NOT NULL,
  url             TEXT   NOT NULL,
  homepage        TEXT,
  description     TEXT,
  logo_url        TEXT,
  language        TEXT,
  license_spdx    TEXT,
  topics          TEXT[] DEFAULT '{}',
  is_archived     BOOLEAN DEFAULT FALSE,
  is_fork         BOOLEAN DEFAULT FALSE,
  ai_relevance    REAL,
  stars           INT DEFAULT 0,
  forks           INT DEFAULT 0,
  watchers        INT DEFAULT 0,
  open_issues     INT DEFAULT 0,
  contributors    INT,
  star_growth_7d  INT DEFAULT 0,
  star_growth_30d INT DEFAULT 0,
  hot_score       REAL DEFAULT 0,
  trending_flag   BOOLEAN DEFAULT FALSE,
  repo_created_at TIMESTAMPTZ,
  repo_pushed_at  TIMESTAMPTZ,
  last_commit_at  TIMESTAMPTZ,
  first_seen_at   TIMESTAMPTZ DEFAULT now(),
  last_crawled_at TIMESTAMPTZ,
  search_vector   TSVECTOR GENERATED ALWAYS AS (
                    setweight(to_tsvector('simple', coalesce(full_name,'')), 'A') ||
                    setweight(to_tsvector('english', coalesce(description,'')), 'B')
                  ) STORED
);

CREATE TABLE IF NOT EXISTS repo_snapshots (
  repo_id       BIGINT REFERENCES repositories(id) ON DELETE CASCADE,
  snapshot_date DATE NOT NULL,
  stars INT, forks INT, watchers INT, open_issues INT, contributors INT,
  PRIMARY KEY (repo_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS categories (
  id            SMALLSERIAL PRIMARY KEY,
  slug          TEXT UNIQUE NOT NULL,
  name          TEXT NOT NULL,
  description   TEXT,
  display_order SMALLINT DEFAULT 100
);

CREATE TABLE IF NOT EXISTS repo_categories (
  repo_id     BIGINT REFERENCES repositories(id) ON DELETE CASCADE,
  category_id SMALLINT REFERENCES categories(id) ON DELETE CASCADE,
  confidence  REAL DEFAULT 1.0,
  source      TEXT CHECK (source IN ('rule','llm','manual')),
  PRIMARY KEY (repo_id, category_id)
);

CREATE TABLE IF NOT EXISTS tags (
  id   SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_tags (
  repo_id BIGINT REFERENCES repositories(id) ON DELETE CASCADE,
  tag_id  INT REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (repo_id, tag_id)
);

CREATE TABLE IF NOT EXISTS ai_summaries (
  id          BIGSERIAL PRIMARY KEY,
  repo_id     BIGINT REFERENCES repositories(id) ON DELETE CASCADE,
  readme_hash TEXT NOT NULL,
  model       TEXT NOT NULL,
  content     JSONB NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (repo_id, readme_hash)
);

CREATE TABLE IF NOT EXISTS repo_mentions (
  id           BIGSERIAL PRIMARY KEY,
  repo_id      BIGINT REFERENCES repositories(id) ON DELETE CASCADE,
  source       TEXT NOT NULL,
  external_id  TEXT NOT NULL,
  title        TEXT, url TEXT, score INT,
  mentioned_at TIMESTAMPTZ,
  UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS crawl_runs (
  id          BIGSERIAL PRIMARY KEY,
  started_at  TIMESTAMPTZ DEFAULT now(),
  finished_at TIMESTAMPTZ,
  trigger     TEXT DEFAULT 'cron',
  status      TEXT CHECK (status IN ('running','success','partial','failed')),
  stats       JSONB DEFAULT '{}',
  error       TEXT
);

CREATE TABLE IF NOT EXISTS raw_items (
  id      BIGSERIAL PRIMARY KEY,
  run_id  BIGINT REFERENCES crawl_runs(id) ON DELETE CASCADE,
  source  TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_repos_hot      ON repositories (hot_score DESC)      WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_repos_stars    ON repositories (stars DESC)          WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_repos_growth7  ON repositories (star_growth_7d DESC) WHERE NOT is_archived;
CREATE INDEX IF NOT EXISTS idx_repos_new      ON repositories (first_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_repos_language ON repositories (language);
CREATE INDEX IF NOT EXISTS idx_repos_fullname ON repositories (full_name);
CREATE INDEX IF NOT EXISTS idx_repos_fts      ON repositories USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_repos_trgm     ON repositories USING GIN (full_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_repos_topics   ON repositories USING GIN (topics);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON repo_snapshots USING BRIN (snapshot_date);
CREATE INDEX IF NOT EXISTS idx_rc_category    ON repo_categories (category_id, repo_id);
CREATE INDEX IF NOT EXISTS idx_mentions_repo  ON repo_mentions (repo_id, mentioned_at DESC);
