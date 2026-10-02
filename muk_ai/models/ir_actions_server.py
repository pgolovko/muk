from __future__ import annotations

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.muk_ai.tools.context import clean_view_context_payload


class IrActionsServer(models.Model):
    """Add the ``ai_session`` server-action state running pending sessions."""

    _inherit = 'ir.actions.server'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    state = fields.Selection(
        selection_add=[
            ('ai_session', 'AI Session Worker'),
            ('ai_start_session', 'Start AI Session'),
        ],
        ondelete={'ai_session': 'cascade', 'ai_start_session': 'cascade'},
    )

    ai_agent_id = fields.Many2one(
        comodel_name='muk_ai.agent',
        string='AI Agent',
        ondelete='set null',
    )

    ai_space_id = fields.Many2one(
        comodel_name='muk_ai.space',
        string='AI Space',
        ondelete='set null',
    )

    ai_prompt = fields.Text(
        string='AI Prompt',
        help='Message the new session is started with.',
    )

    @api.constrains('state', 'ai_agent_id', 'ai_prompt')
    def _check_ai_start_session(self) -> None:
        for action in self.filtered(lambda a: a.state == 'ai_start_session'):
            if not action.ai_agent_id or not (action.ai_prompt or '').strip():
                raise ValidationError(
                    _('Starting an AI session requires an agent and a prompt.')
                )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _run_action_ai_session(self, eval_context=None) -> None:
        """Run pending AI sessions for a single-record server action."""
        self.env['muk_ai.session']._cron_run_pending_sessions()

    def _run_action_ai_session_multi(self, eval_context=None) -> None:
        """Run pending AI sessions for a multi-record server action."""
        self.env['muk_ai.session']._cron_run_pending_sessions()

    def _run_action_ai_start_session(self, eval_context=None) -> None:
        """Create a session for the selected agent/space and start it."""
        self.ensure_one()
        session = self.env['muk_ai.session'].create(
            {
                'agent_id': self.ai_agent_id.id,
                'space_id': self.ai_space_id.id or False,
                'name': self.ai_prompt[:50] if self.ai_prompt else 'New AI Session',
                'override_approval_mode': 'off',
            }
        )
        if payload := self._ai_record_view_context(eval_context):
            session._write_view_context(clean_view_context_payload('record', payload))
        session.start(self.ai_prompt)
        return False

    def _ai_record_view_context(self, eval_context=None) -> dict | None:
        """Return a record view-context payload for the triggering record."""
        record = (eval_context or {}).get('record')
        if not record:
            model = self.env.context.get('active_model')
            res_id = self.env.context.get('active_id')
            if not model or not res_id or model not in self.env:
                return None
            record = self.env[model].browse(res_id)
        record = record[:1].exists()
        if not record or not record.has_access('read'):
            return None
        return {
            'kind': 'record',
            'model': record._name,
            'id': record.id,
            'display_name': record.display_name,
        }
