CREATE TABLE users (
  id          BIGINT       PRIMARY KEY,
  email       VARCHAR(255) NOT NULL UNIQUE,
  created_at  TIMESTAMP    NOT NULL
);

CREATE TABLE events (
  id          BIGINT       PRIMARY KEY,
  user_id     BIGINT       NOT NULL REFERENCES users (id),
  kind        VARCHAR(32)  NOT NULL,
  created_at  TIMESTAMP    NOT NULL
);
