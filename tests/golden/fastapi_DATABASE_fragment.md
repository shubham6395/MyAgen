### User (`users`, sqlalchemy) — models.py:7

| Field | Type | Nullable | Key | Default | Constraints |
|---|---|---|---|---|---|
| id | Integer |  | PK |  | index |
| email | String | no |  |  | unique |
| is_active | Boolean |  |  | True |  |

### Item (`items`, sqlalchemy) — models.py:17

| Field | Type | Nullable | Key | Default | Constraints |
|---|---|---|---|---|---|
| id | Integer |  | PK |  |  |
| name | String | no |  |  |  |
| owner_id | Integer |  |  |  | ForeignKey('users.id') |