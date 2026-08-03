BEGIN;

CREATE TABLE reference_relation (
    reference_relation_id text PRIMARY KEY CHECK (reference_relation_id ~ '^rrl_[a-z0-9]{12,}$'),
    source_reference_id text NOT NULL REFERENCES versification_reference(versification_reference_id),
    target_reference_id text NOT NULL REFERENCES versification_reference(versification_reference_id),
    relation_type text NOT NULL CHECK (relation_type IN ('equivalent','split','join','overlap','omitted','addition','relocated','uncertain')),
    confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    method text NOT NULL,
    review_state text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source_reference_id <> target_reference_id),
    UNIQUE (source_reference_id, target_reference_id, relation_type)
);

CREATE INDEX reference_relation_source_idx
    ON reference_relation(source_reference_id, relation_type);
CREATE INDEX reference_relation_target_idx
    ON reference_relation(target_reference_id, relation_type);

COMMIT;
