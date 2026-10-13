-- Supabase Migration: Lovira-Facebook Manager Licensing Backend
-- Tuân thủ Đặc tả Mục 14 (Schema, RLS, Edge Functions & RPCs)

-- 1. Bảng cấu hình hệ thống
CREATE TABLE IF NOT EXISTS public.app_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    license_required BOOLEAN NOT NULL DEFAULT true,
    max_active_sessions_global INTEGER, -- null = không giới hạn trần
    default_max_sessions_per_license INTEGER NOT NULL DEFAULT 1,
    allow_device_transfer BOOLEAN NOT NULL DEFAULT true,
    heartbeat_interval_seconds INTEGER NOT NULL DEFAULT 60,
    session_ttl_seconds INTEGER NOT NULL DEFAULT 180,
    free_features JSONB NOT NULL DEFAULT '{"view_local_data": true, "compose_drafts": true, "export_backup": true, "download_video": false, "publish_post": false}'::jsonb,
    feature_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    maintenance_mode BOOLEAN NOT NULL DEFAULT false,
    maintenance_message TEXT NOT NULL DEFAULT 'Hệ thống đang bảo trì.',
    contact_info JSONB NOT NULL DEFAULT '{"support_name": "Lovira Support", "hotline": "0988-xxx-xxx", "zalo": "https://zalo.me/lovira", "email": "support@lovira.vn", "website": "https://lovira.vn"}'::jsonb,
    min_app_version TEXT NOT NULL DEFAULT '0.1.0',
    latest_app_version TEXT NOT NULL DEFAULT '0.1.0',
    config_version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 2. Bảng quản lý License Key
CREATE TABLE IF NOT EXISTS public.licenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_digest TEXT NOT NULL UNIQUE, -- SHA-256 / HMAC của License Key
    key_hint TEXT NOT NULL, -- 4 ký tự cuối để hiển thị hỗ trợ
    status TEXT NOT NULL DEFAULT 'active', -- 'active', 'suspended', 'revoked', 'expired'
    plan TEXT NOT NULL DEFAULT 'standard',
    starts_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    expires_at TIMESTAMPTZ NOT NULL,
    max_sessions INTEGER NOT NULL DEFAULT 1,
    allow_transfer BOOLEAN NOT NULL DEFAULT true,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3. Bảng thiết bị
CREATE TABLE IF NOT EXISTS public.devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    install_id TEXT NOT NULL UNIQUE,
    fingerprint_digest TEXT NOT NULL,
    os_name TEXT,
    app_version TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 4. Bảng phiên License đang hoạt động
CREATE TABLE IF NOT EXISTS public.license_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    license_id UUID NOT NULL REFERENCES public.licenses(id) ON DELETE CASCADE,
    device_id UUID NOT NULL REFERENCES public.devices(id) ON DELETE CASCADE,
    generation INTEGER NOT NULL DEFAULT 1,
    token_digest TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);
CREATE INDEX IF NOT EXISTS idx_license_sessions_active ON public.license_sessions(license_id, revoked_at, expires_at);

-- 5. Bảng phiên miễn phí
CREATE TABLE IF NOT EXISTS public.free_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id UUID NOT NULL REFERENCES public.devices(id) ON DELETE CASCADE,
    token_digest TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 6. Bảng nhật ký thay đổi quản trị
CREATE TABLE IF NOT EXISTS public.admin_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id TEXT,
    action TEXT NOT NULL,
    target_id TEXT,
    change_summary JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- KÍCH HOẠT ROW LEVEL SECURITY (RLS) - BẢO VỆ CHẶT CHẼ (AC-30)
ALTER TABLE public.app_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.licenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.license_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.free_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_audit_logs ENABLE ROW LEVEL SECURITY;

-- Policy: Client nặc danh (anon) chỉ được SELECT app_config công khai
DROP POLICY IF EXISTS "Public can view app config" ON public.app_config;
CREATE POLICY "Public can view app config" ON public.app_config
    FOR SELECT USING (true);

-- Client anon KHÔNG được phép đọc hay sửa trực tiếp bảng licenses, license_sessions!
-- Toàn bộ việc cấp phiên phải qua SECURITY DEFINER RPC functions bên dưới.

-- HÀM KÍCH HOẠT BẢN QUYỀN NGUYÊN TỬ (RPC: activate_license_rpc)
CREATE OR REPLACE FUNCTION public.activate_license_rpc(
    p_key_digest TEXT,
    p_install_id TEXT,
    p_fingerprint TEXT,
    p_os_name TEXT,
    p_app_version TEXT,
    p_force_transfer BOOLEAN
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_license public.licenses%ROWTYPE;
    v_device_id UUID;
    v_active_session public.license_sessions%ROWTYPE;
    v_config public.app_config%ROWTYPE;
    v_new_session_id UUID;
    v_new_generation INTEGER := 1;
    v_token TEXT;
    v_ttl_interval INTERVAL;
BEGIN
    -- 1. Lấy cấu hình hệ thống
    SELECT * INTO v_config FROM public.app_config WHERE id = 1;
    IF v_config.maintenance_mode THEN
        RETURN jsonb_build_object('success', false, 'error_code', 'MAINTENANCE_MODE', 'message', v_config.maintenance_message);
    END IF;

    v_ttl_interval := make_interval(secs => COALESCE(v_config.session_ttl_seconds, 180));

    -- 2. Tìm và khóa nguyên tử dòng license (FOR UPDATE)
    SELECT * INTO v_license FROM public.licenses WHERE key_digest = p_key_digest FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('success', false, 'error_code', 'KEY_NOT_FOUND', 'message', 'License Key không hợp lệ.');
    END IF;

    IF v_license.status != 'active' THEN
        RETURN jsonb_build_object('success', false, 'error_code', 'KEY_BLOCKED', 'message', 'License Key đã bị khóa hoặc hết hạn.');
    END IF;

    IF v_license.expires_at < now() THEN
        RETURN jsonb_build_object('success', false, 'error_code', 'KEY_EXPIRED', 'message', 'License Key đã hết hạn sử dụng.');
    END IF;

    -- 3. Tạo hoặc cập nhật thiết bị
    INSERT INTO public.devices (install_id, fingerprint_digest, os_name, app_version, last_seen_at)
    VALUES (p_install_id, p_fingerprint, p_os_name, p_app_version, now())
    ON CONFLICT (install_id) DO UPDATE SET
        fingerprint_digest = EXCLUDED.fingerprint_digest,
        os_name = EXCLUDED.os_name,
        app_version = EXCLUDED.app_version,
        last_seen_at = now()
    RETURNING id INTO v_device_id;

    -- 4. Kiểm tra phiên đang hoạt động của license
    SELECT * INTO v_active_session
    FROM public.license_sessions
    WHERE license_id = v_license.id AND revoked_at IS NULL AND expires_at > now()
    ORDER BY created_at DESC LIMIT 1;

    IF FOUND AND v_active_session.device_id != v_device_id THEN
        IF NOT p_force_transfer THEN
            RETURN jsonb_build_object(
                'success', false,
                'error_code', 'DEVICE_TRANSFER_REQUIRED',
                'message', 'Key đang hoạt động trên máy khác. Bạn có muốn chuyển phiên sang máy này không?',
                'requires_transfer_confirmation', true
            );
        END IF;

        -- Thu hồi phiên của máy cũ ngay lập tức (AC-23, AC-24)
        UPDATE public.license_sessions
        SET revoked_at = now()
        WHERE id = v_active_session.id;

        v_new_generation := v_active_session.generation + 1;
    ELSIF FOUND AND v_active_session.device_id = v_device_id THEN
        v_new_generation := v_active_session.generation + 1;
        UPDATE public.license_sessions SET revoked_at = now() WHERE id = v_active_session.id;
    END IF;

    -- 5. Tạo phiên mới
    v_new_session_id := gen_random_uuid();
    v_token := encode(gen_random_bytes(32), 'hex');

    INSERT INTO public.license_sessions (id, license_id, device_id, generation, token_digest, expires_at)
    VALUES (v_new_session_id, v_license.id, v_device_id, v_new_generation, encode(digest(v_token, 'sha256'), 'hex'), now() + v_ttl_interval);

    RETURN jsonb_build_object(
        'success', true,
        'session_id', v_new_session_id,
        'generation', v_new_generation,
        'session_token', v_token,
        'license_key_hint', v_license.key_hint,
        'expires_at', to_char(v_license.expires_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
        'config_version', v_config.config_version
    );
END;
$$;

-- HÀM HEARTBEAT GIA HẠN LEASE NGUYÊN TỬ (RPC: heartbeat_session_rpc)
CREATE OR REPLACE FUNCTION public.heartbeat_session_rpc(
    p_session_id UUID,
    p_generation INTEGER,
    p_token_digest TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_session public.license_sessions%ROWTYPE;
    v_license public.licenses%ROWTYPE;
    v_config public.app_config%ROWTYPE;
    v_new_expires TIMESTAMPTZ;
BEGIN
    SELECT * INTO v_config FROM public.app_config WHERE id = 1;
    SELECT * INTO v_session FROM public.license_sessions WHERE id = p_session_id;

    IF NOT FOUND OR v_session.revoked_at IS NOT NULL THEN
        RETURN jsonb_build_object('success', false, 'is_revoked', true, 'message', 'Phiên đã bị thu hồi.');
    END IF;

    -- Kiểm tra generation chống heartbeat từ thế hệ cũ
    IF v_session.generation != p_generation THEN
        RETURN jsonb_build_object('success', false, 'is_revoked', true, 'message', 'Thế hệ phiên không khớp.');
    END IF;

    SELECT * INTO v_license FROM public.licenses WHERE id = v_session.license_id;
    IF v_license.expires_at < now() OR v_license.status != 'active' THEN
        RETURN jsonb_build_object('success', false, 'is_expired', true, 'message', 'Bản quyền đã hết hạn.');
    END IF;

    -- Gia hạn lease (không vượt quá hạn của license)
    v_new_expires := LEAST(now() + make_interval(secs => COALESCE(v_config.session_ttl_seconds, 180)), v_license.expires_at);

    UPDATE public.license_sessions
    SET expires_at = v_new_expires, last_seen_at = now()
    WHERE id = p_session_id;

    RETURN jsonb_build_object(
        'success', true,
        'is_revoked', false,
        'is_expired', false,
        'generation', v_session.generation,
        'new_expires_at', to_char(v_new_expires, 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    );
END;
$$;
