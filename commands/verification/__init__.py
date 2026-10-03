"""Rules-agreement verification command domain (renamed from /rules_agreement
to /verify, and moved out of the old reaction_commands.py -- unrelated to
the reaction-check domain despite the old shared file)."""
from commands.verification.commands import RulesAgreementGroup
from commands.verification.context_menus import track_rules_message_ctx, untrack_rules_message_ctx

VERIFICATION_CONTEXT_MENUS = [
    track_rules_message_ctx,
    untrack_rules_message_ctx,
]

__all__ = ['RulesAgreementGroup', 'VERIFICATION_CONTEXT_MENUS']
