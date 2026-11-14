-- EGSA DIGITAL EQUB REGISTRATION DATABASE
-- PostgreSQL / Supabase
-- Maximum members per group: 10
-- =====================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Equb groups
CREATE TABLE IF NOT EXISTS public.equb_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_name VARCHAR(150) NOT NULL,
    capacity INTEGER NOT NULL DEFAULT 10
        CHECK (capacity = 10),
    is_open BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_equb_default_group
ON public.equb_groups (is_default)
WHERE is_default = TRUE;

-- 2. Equb members
CREATE TABLE IF NOT EXISTS public.equb_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL
        REFERENCES public.equb_groups(id),
    member_no INTEGER NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    telegram_username VARCHAR(60),
    registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_equb_member_number
        UNIQUE (group_id, member_no),

    CONSTRAINT uq_equb_member_phone
        UNIQUE (group_id, phone),

    CONSTRAINT chk_equb_member_number
        CHECK (member_no BETWEEN 1 AND 10)
);

-- 3. Create initial group
INSERT INTO public.equb_groups (
    group_name,
    capacity,
    is_open,
    is_default
)
SELECT
    'EGSA Digital Equb - Group 1',
    10,
    TRUE,
    TRUE
WHERE NOT EXISTS (
    SELECT 1
    FROM public.equb_groups
    WHERE is_default = TRUE
);

-- 4. Enable Row Level Security
ALTER TABLE public.equb_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.equb_members ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.equb_groups FROM anon, authenticated;
REVOKE ALL ON public.equb_members FROM anon, authenticated;

-- 5. Registration function
CREATE OR REPLACE FUNCTION public.register_equb_member(
    p_full_name TEXT,
    p_phone TEXT,
    p_telegram_username TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_group public.equb_groups%ROWTYPE;
    v_count INTEGER;
    v_member_no INTEGER;
BEGIN

    -- Validate input
    IF p_full_name IS NULL OR LENGTH(TRIM(p_full_name)) = 0 THEN
        RETURN jsonb_build_object('status', 'invalid_name');
    END IF;

    IF p_phone IS NULL OR LENGTH(TRIM(p_phone)) = 0 THEN
        RETURN jsonb_build_object('status', 'invalid_phone');
    END IF;

    -- Lock the group to prevent concurrent over-registration
    SELECT *
    INTO v_group
    FROM public.equb_groups
    WHERE is_default = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'closed');
    END IF;

    IF NOT v_group.is_open THEN
        RETURN jsonb_build_object('status', 'closed');
    END IF;

    -- Reject duplicate phone numbers
    IF EXISTS (
        SELECT 1
        FROM public.equb_members
        WHERE group_id = v_group.id
          AND phone = TRIM(p_phone)
    ) THEN
        RETURN jsonb_build_object('status', 'duplicate');
    END IF;

    -- Count current members
    SELECT COUNT(*)
    INTO v_count
    FROM public.equb_members
    WHERE group_id = v_group.id;

    -- Reject if full
    IF v_count >= v_group.capacity THEN
        UPDATE public.equb_groups
        SET is_open = FALSE
        WHERE id = v_group.id;

        RETURN jsonb_build_object('status', 'full');
    END IF;

    v_member_no := v_count + 1;

    -- Register member
    INSERT INTO public.equb_members (
        group_id,
        member_no,
        full_name,
        phone,
        telegram_username
    )
    VALUES (
        v_group.id,
        v_member_no,
        TRIM(p_full_name),
        TRIM(p_phone),
        NULLIF(TRIM(COALESCE(p_telegram_username, '')), '')
    );

    -- Automatically close at member 10
    IF v_member_no = v_group.capacity THEN
        UPDATE public.equb_groups
        SET is_open = FALSE
        WHERE id = v_group.id;
    END IF;

    RETURN jsonb_build_object(
        'status', 'registered',
        'member_no', v_member_no,
        'remaining', v_group.capacity - v_member_no
    );

EXCEPTION
    WHEN unique_violation THEN
        RETURN jsonb_build_object('status', 'duplicate');
END;
$$;

-- 6. Public registration permission
REVOKE ALL ON FUNCTION
public.register_equb_member(TEXT, TEXT, TEXT)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
public.register_equb_member(TEXT, TEXT, TEXT)
TO anon, authenticated;
