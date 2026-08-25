"""Rules-agreement verification command domain (renamed from /rules_agreement
to /verify, and moved out of the old reaction_commands.py -- unrelated to
the reaction-check domain despite the old shared file)."""
from commands.verification.commands import RulesAgreementGroup

__all__ = ['RulesAgreementGroup']
