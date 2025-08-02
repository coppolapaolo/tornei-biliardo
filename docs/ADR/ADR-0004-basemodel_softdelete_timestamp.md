# ADR-0004: BaseModel, SoftDelete e TimestampMixin

Data: 2025-08-01

## Stato
Accettato

## Contesto
Pattern ripetuti fra i modelli: `id`, `created_at`, `updated_at`, eliminazione logica. Serviva anche tenere traccia storica di match e statistiche.

## Decisione
* Creare `BaseModel` con `id` UUID primario e metodo helper `to_dict`.
* `TimestampMixin` aggiorna automaticamente `created_at`/`updated_at` via events SQLAlchemy.
* `SoftDeleteMixin` aggiunge `is_deleted` e modifica il default query per escludere record eliminati.
* Tutti i nuovi modelli ereditano da questi mixin.

## Conseguenze
+ Schema DRY e auditing coerente.
+ Disponibile `hard_delete()` quando serve rimozione fisica.
− Piccolo overhead dovuto agli event listener.

## Alternative
*Trigger DB* – non portabile su SQLite dev.
*Nessun soft delete* – viola requisiti di audit.
