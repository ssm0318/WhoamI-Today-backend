-- PostgreSQL 초기 설정

-- 사용자 확인 후 없으면 생성
DO
$$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'postgres') THEN
        CREATE USER postgres WITH PASSWORD 'postgres';
    ELSE
        ALTER USER postgres WITH PASSWORD 'postgres';
    END IF;
END
$$;

-- 데이터베이스 생성 (따로 실행)
SELECT 'CREATE DATABASE diivers'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'diivers')\gexec

-- postgres 사용자에게 권한 부여
ALTER ROLE postgres SET client_encoding TO 'utf-8';
ALTER ROLE postgres SET timezone TO 'America/Los_Angeles';
GRANT ALL PRIVILEGES ON DATABASE diivers TO postgres;