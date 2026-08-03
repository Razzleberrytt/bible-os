BEGIN;

CREATE TABLE source (
    source_id text PRIMARY KEY CHECK (source_id ~ '^src_[a-z0-9]{12,}$'),
    name text NOT NULL,
    source_type text NOT NULL,
    authority_status text NOT NULL,
    license_status text NOT NULL,
    commercial_use text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE acquisition_event (
    acquisition_event_id text PRIMARY KEY CHECK (acquisition_event_id ~ '^acq_[a-z0-9]{12,}$'),
    source_id text NOT NULL REFERENCES source(source_id),
    requested_url text NOT NULL,
    resolved_url text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    result text NOT NULL CHECK (result IN ('success','failed','quarantined','rejected')),
    observed_sha256 char(64) CHECK (observed_sha256 ~ '^[a-f0-9]{64}$'),
    observed_bytes bigint CHECK (observed_bytes >= 0),
    retrieval_tool jsonb NOT NULL,
    error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source_artifact (
    artifact_id text PRIMARY KEY CHECK (artifact_id ~ '^art_[a-z0-9]{12,}$'),
    source_id text NOT NULL REFERENCES source(source_id),
    acquisition_event_id text NOT NULL REFERENCES acquisition_event(acquisition_event_id),
    sha256 char(64) NOT NULL UNIQUE CHECK (sha256 ~ '^[a-f0-9]{64}$'),
    byte_size bigint NOT NULL CHECK (byte_size > 0),
    media_type text NOT NULL,
    filename text NOT NULL,
    archive_uri text NOT NULL UNIQUE,
    verification_status text NOT NULL CHECK (verification_status IN ('verified','quarantined','rejected')),
    license_assertion jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE work (
    work_id text PRIMARY KEY CHECK (work_id ~ '^wrk_[a-z0-9]{12,}$'),
    canonical_name text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE book (
    book_id text PRIMARY KEY CHECK (book_id ~ '^bok_[a-z0-9]{12,}$'),
    work_id text NOT NULL REFERENCES work(work_id),
    canonical_name text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE passage (
    passage_id text PRIMARY KEY CHECK (passage_id ~ '^pas_[a-z0-9]{12,}$'),
    book_id text NOT NULL REFERENCES book(book_id),
    parent_passage_id text REFERENCES passage(passage_id),
    passage_kind text NOT NULL CHECK (passage_kind IN ('book','chapter','verse','superscription','segment','addition','omission-locus','other')),
    sort_ordinal bigint NOT NULL CHECK (sort_ordinal >= 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX passage_book_sort_idx ON passage(book_id, sort_ordinal);

CREATE TABLE versification_system (
    versification_system_id text PRIMARY KEY CHECK (versification_system_id ~ '^vrs_[a-z0-9]{12,}$'),
    name text NOT NULL,
    version text NOT NULL,
    authority text,
    UNIQUE (name, version)
);

CREATE TABLE versification_reference (
    versification_reference_id text PRIMARY KEY CHECK (versification_reference_id ~ '^ref_[a-z0-9]{12,}$'),
    versification_system_id text NOT NULL REFERENCES versification_system(versification_system_id),
    book_code text NOT NULL,
    chapter integer CHECK (chapter > 0),
    verse integer CHECK (verse >= 0),
    subverse text,
    display_reference text NOT NULL,
    source_locator jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (versification_system_id, book_code, chapter, verse, subverse)
);

CREATE TABLE passage_reference_mapping (
    passage_reference_mapping_id text PRIMARY KEY CHECK (passage_reference_mapping_id ~ '^prm_[a-z0-9]{12,}$'),
    passage_id text NOT NULL REFERENCES passage(passage_id),
    versification_reference_id text NOT NULL REFERENCES versification_reference(versification_reference_id),
    relation_type text NOT NULL CHECK (relation_type IN ('equivalent','split','join','overlap','omitted','addition','relocated','uncertain')),
    confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    method text NOT NULL,
    review_state text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (passage_id, versification_reference_id, relation_type)
);

CREATE TABLE corpus (
    corpus_id text PRIMARY KEY CHECK (corpus_id ~ '^cor_[a-z0-9]{12,}$'),
    source_id text NOT NULL REFERENCES source(source_id),
    name text NOT NULL,
    upstream_version text,
    language_codes text[] NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE corpus_artifact (
    corpus_id text NOT NULL REFERENCES corpus(corpus_id),
    artifact_id text NOT NULL REFERENCES source_artifact(artifact_id),
    PRIMARY KEY (corpus_id, artifact_id)
);

CREATE TABLE text_unit (
    text_unit_id text PRIMARY KEY CHECK (text_unit_id ~ '^txt_[a-z0-9]{12,}$'),
    corpus_id text NOT NULL REFERENCES corpus(corpus_id),
    passage_id text NOT NULL REFERENCES passage(passage_id),
    source_reference_id text REFERENCES versification_reference(versification_reference_id),
    realization_type text NOT NULL CHECK (realization_type IN ('text','empty-placeholder','explicit-omission','addition','uncertain')),
    source_text text,
    normalized_text text,
    source_sequence integer NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (corpus_id, source_sequence),
    CHECK ((realization_type = 'text' AND source_text IS NOT NULL) OR realization_type <> 'text')
);
CREATE INDEX text_unit_passage_idx ON text_unit(passage_id, corpus_id);

CREATE TABLE alignment (
    alignment_id text PRIMARY KEY CHECK (alignment_id ~ '^aln_[a-z0-9]{12,}$'),
    alignment_level text NOT NULL CHECK (alignment_level IN ('passage','text-unit','segment','token')),
    source_ids text[] NOT NULL,
    target_ids text[] NOT NULL,
    relation_type text NOT NULL CHECK (relation_type IN ('equivalent','split','join','overlap','omitted','addition','relocated','uncertain')),
    method text NOT NULL,
    algorithm_version text,
    confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    review_state text NOT NULL,
    provenance jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_report (
    validation_report_id text PRIMARY KEY CHECK (validation_report_id ~ '^val_[a-z0-9]{12,}$'),
    profile text NOT NULL,
    status text NOT NULL CHECK (status IN ('passed','failed','provisional')),
    critical_failures integer NOT NULL DEFAULT 0 CHECK (critical_failures >= 0),
    report_sha256 char(64) NOT NULL CHECK (report_sha256 ~ '^[a-f0-9]{64}$'),
    report_uri text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dataset_release (
    release_id text PRIMARY KEY CHECK (release_id ~ '^rel_[a-z0-9]{12,}$'),
    version text NOT NULL UNIQUE,
    status text NOT NULL CHECK (status IN ('provisional','approved','withdrawn')),
    schema_version text NOT NULL,
    pipeline_revision text NOT NULL,
    release_manifest_sha256 char(64) NOT NULL UNIQUE CHECK (release_manifest_sha256 ~ '^[a-f0-9]{64}$'),
    release_manifest_uri text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION bible_os_prevent_update_delete() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER source_artifact_immutable
BEFORE UPDATE OR DELETE ON source_artifact
FOR EACH ROW EXECUTE FUNCTION bible_os_prevent_update_delete();

CREATE TRIGGER acquisition_event_immutable
BEFORE UPDATE OR DELETE ON acquisition_event
FOR EACH ROW EXECUTE FUNCTION bible_os_prevent_update_delete();

COMMIT;
