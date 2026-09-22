-- Migration 019: localize persisted interaction-derived tags to Chinese.
--
-- Internal ids in interaction_classification remain unchanged. Only the
-- user-facing chat_content_tags array is translated, with non-taxonomy tags
-- preserved for compatibility with older free-form extraction.
UPDATE events
SET chat_content_tags = (
    SELECT json_group_array(translated)
    FROM (
        SELECT
            CASE value
                WHEN 'past_event_recount' THEN '过去事件简述'
                WHEN 'present_situation_commentary' THEN '现状描述'
                WHEN 'general_information_explanation' THEN '信息解释'
                WHEN 'future_event_intention' THEN '未来意图'
                WHEN 'opinion' THEN '观点'
                WHEN 'evaluation' THEN '评价'
                WHEN 'feeling_emotion' THEN '情绪表达'
                WHEN 'observation_comment' THEN '观察评论'
                WHEN 'complaint_grievance' THEN '抱怨'
                WHEN 'chat_small_talk' THEN '闲聊'
                WHEN 'gossip' THEN '八卦'
                WHEN 'catching_up' THEN '叙旧'
                WHEN 'relationship_oriented_talk' THEN '关系交流'
                WHEN 'narrative' THEN '完整叙事'
                WHEN 'anecdote' THEN '轶事'
                WHEN 'storytelling_recount' THEN '过程复述'
                WHEN 'exemplum' THEN '例证故事'
                WHEN 'joking' THEN '玩笑'
                WHEN 'banter_teasing' THEN '调侃'
                WHEN 'friendly_ridicule' THEN '善意嘲弄'
                WHEN 'exploring_understanding' THEN '探索理解'
                WHEN 'problem_solving' THEN '问题解决'
                WHEN 'considering_options' THEN '方案比较'
                WHEN 'planning' THEN '规划'
                WHEN 'decision_oriented_discussion' THEN '决策讨论'
                WHEN 'advice' THEN '建议'
                WHEN 'suggestion' THEN '提议'
                WHEN 'instruction' THEN '操作指导'
                WHEN 'difference_of_opinion' THEN '意见分歧'
                WHEN 'debate' THEN '辩论'
                WHEN 'interpersonal_conflict' THEN '人际冲突'
                WHEN 'information_seeking' THEN '信息询问'
                WHEN 'action_request' THEN '行动请求'
                WHEN 'uncategorised' THEN '未分类'
                ELSE value
            END AS translated,
            MIN(CAST(key AS INTEGER)) AS first_position
        FROM json_each(events.chat_content_tags)
        GROUP BY translated
        ORDER BY first_position
    )
)
WHERE EXISTS (
    SELECT 1
    FROM json_each(events.chat_content_tags)
    WHERE value IN (
        'past_event_recount', 'present_situation_commentary',
        'general_information_explanation', 'future_event_intention',
        'opinion', 'evaluation', 'feeling_emotion', 'observation_comment',
        'complaint_grievance', 'chat_small_talk', 'gossip', 'catching_up',
        'relationship_oriented_talk', 'narrative', 'anecdote',
        'storytelling_recount', 'exemplum', 'joking', 'banter_teasing',
        'friendly_ridicule', 'exploring_understanding', 'problem_solving',
        'considering_options', 'planning', 'decision_oriented_discussion',
        'advice', 'suggestion', 'instruction', 'difference_of_opinion',
        'debate', 'interpersonal_conflict', 'information_seeking',
        'action_request', 'uncategorised'
    )
);
