-- Holder-scoped views: the ONLY tables an NPC or assistant prompt builder may read.
-- They are TEMP views over a one-row TEMP table `ctx` (who, t), created per connection, and each
-- is self-contained (no nested views) so that the authorizer in design/schema.md section 6.2
-- can allow base-table reads only when they come from one of these views.
-- Columns that must never reach a holder (`about`, `sincerity`, hidden state) are not exposed.

-- @@holder
CREATE TEMP TABLE ctx (who TEXT NOT NULL, t INTEGER NOT NULL);

CREATE TEMP VIEW v_knows AS
SELECT k.id, r.body, r.t_from AS learned, k.channel, k.source, s.name AS source_name, k.hops,
       COALESCE((SELECT b.stance FROM belief_update b JOIN record br ON br.id = b.id
                 WHERE b.knowledge_id = k.id AND br.t_from <= ctx.t
                   AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = br.id)
                 ORDER BY br.t_from DESC, br.id DESC LIMIT 1), k.stance) AS stance,
       k.salience,
       EXISTS (SELECT 1 FROM record_link l JOIN record sr ON sr.id = l.child
               WHERE l.parent = k.id AND l.role = 'about' AND sr.kind = 'surfaced'
                 AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = sr.id)) AS surfaced
FROM ctx, knowledge k JOIN record r ON r.id = k.id LEFT JOIN entity s ON s.id = k.source
WHERE k.holder = ctx.who AND r.t_from <= ctx.t
  AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = r.id);

CREATE TEMP VIEW v_own_state AS
SELECT r.id, s.category, s.elem, r.body, r.t_from AS since
FROM ctx, record r JOIN state_elem s ON s.id = r.id
WHERE r.kind = 'state' AND s.subject = ctx.who AND r.t_from <= ctx.t
  AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = r.id)
  AND r.id = (SELECT x.id FROM record x WHERE x.kind = 'state' AND x.slot = r.slot AND x.t_from <= ctx.t
              AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = x.id)
              ORDER BY x.t_from DESC, x.id DESC LIMIT 1)
  AND s.present = 1 AND (s.expires_at IS NULL OR s.expires_at > ctx.t)
  AND s.self_aware != 'unaware';

CREATE TEMP VIEW v_attitudes AS
SELECT a.id, a.stance, a.magnitude, kr.body AS about_version
FROM ctx, record r JOIN attitude a ON a.id = r.id JOIN record kr ON kr.id = a.knowledge_id
WHERE r.kind = 'attitude' AND a.holder = ctx.who AND r.t_from <= ctx.t
  AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = r.id)
  AND r.id = (SELECT x.id FROM record x WHERE x.kind = 'attitude' AND x.slot = r.slot AND x.t_from <= ctx.t
              AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = x.id)
              ORDER BY x.t_from DESC, x.id DESC LIMIT 1);

CREATE TEMP VIEW v_intents AS
SELECT i.id, i.type, i.audience, r.body
FROM ctx, intent i JOIN record r ON r.id = i.id
WHERE i.holder = ctx.who AND r.t_from <= ctx.t
  AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = r.id)
  AND NOT EXISTS (SELECT 1 FROM intent_resolution x JOIN record xr ON xr.id = x.id
                  WHERE x.intent_id = i.id
                    AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = xr.id));

CREATE TEMP VIEW v_heard_text AS
SELECT r.id, r.kind, t.actor, r.body, r.t_from AS at
FROM ctx, text_unit t JOIN record r ON r.id = t.id
WHERE t.shown = 1 AND r.kind IN ('utterance', 'action', 'player_input') AND r.t_from <= ctx.t
  AND ctx.who IN (SELECT value FROM json_each(t.audience))
  AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = r.id);

CREATE TEMP VIEW v_scene AS
SELECT p.entity, p.place, p.zone
FROM ctx, record r JOIN presence p ON p.id = r.id
WHERE r.kind = 'presence' AND r.t_from <= ctx.t AND p.zone != 'away'
  AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = r.id)
  AND r.id = (SELECT x.id FROM record x WHERE x.kind = 'presence' AND x.slot = r.slot AND x.t_from <= ctx.t
              AND NOT EXISTS (SELECT 1 FROM rollback d WHERE d.record_id = x.id)
              ORDER BY x.t_from DESC, x.id DESC LIMIT 1);
