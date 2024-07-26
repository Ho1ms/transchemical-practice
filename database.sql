CREATE TABLE IF NOT EXISTS brands (
	id SERIAL PRIMARY KEY,
	name VARCHAR(128) NOT NULL DEFAULT '- грузовые',
	code VARCHAR(64) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS detail_categories (
	id SERIAL PRIMARY KEY,
	name VARCHAR(128) NOT NULL
);

CREATE TABLE IF NOT EXISTS details (
	id SERIAL PRIMARY KEY,
	serial_number VARCHAR(64) NOT NULL,
	name VARCHAR(256) NOT NULL,
	description VARCHAR(256) NOT NULL,
	price INTEGER NOT NULL DEFAULT 0,
	model_id INTEGER NOT NULL,
	category_id INTEGER NOT NULL,
	actual_in TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
	
	FOREIGN KEY (model_id) REFERENCES brands(id),
	FOREIGN KEY (category_id) REFERENCES detail_categories(id),
	UNIQUE(model_id, serial_number)
);

CREATE TABLE IF NOT EXISTS personal (
	id BIGINT PRIMARY KEY,
	type VARCHAR(32) not null,
	status VARCHAR(32) not null,
	parent_id BIGINT NOT null,
	name VARCHAR(256) not null
);

CREATE TABLE IF NOT EXISTS logs (
	id BIGINT PRIMARY KEY,
	logtime TIMESTAMP NOT NULL,
	direction VARCHAR(8) NOT NULL,
	devhint int not null,
	emphint bigint not null
);

