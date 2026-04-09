-- Network Advisor: Initial Schema + Seed Data
-- Executed by PostgreSQL on first boot via /docker-entrypoint-initdb.d/

CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    hostname VARCHAR(100) NOT NULL UNIQUE,
    ip_address VARCHAR(15) NOT NULL UNIQUE,
    device_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE services (
    id SERIAL PRIMARY KEY,
    device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    port INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_device_service_name UNIQUE (device_id, name)
);

CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    device_id INTEGER REFERENCES devices(id),
    service_id INTEGER REFERENCES services(id),
    severity VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Seed data: 5 known Camelot network devices
INSERT INTO devices (hostname, ip_address, device_type, status) VALUES
    ('HOLYGRAIL',       '192.168.10.129', 'server',       'unknown'),
    ('Torrentbox',      '192.168.10.141', 'raspberry_pi', 'unknown'),
    ('NAS',             '192.168.10.105', 'raspberry_pi', 'unknown'),
    ('Pi-hole DNS',     '192.168.10.150', 'raspberry_pi', 'unknown'),
    ('Mac Workstation', '192.168.10.145', 'workstation',  'unknown');
