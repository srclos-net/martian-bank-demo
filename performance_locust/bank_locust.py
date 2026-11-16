# Combines the upstream per-flow locust files into a single virtual-user
# population. Each upstream file defines its user class as `MyUser`, which
# locust rejects when multiple files are combined ("Duplicate user class
# names"), so each is wrapped as a uniquely named subclass. The task
# sequences, env-var hosts and wait-times are inherited unchanged.

import auth_locust
import atm_locust
import account_locust
import transaction_locust
import loan_locust


class AuthUser(auth_locust.MyUser):
    """register / login flow (customer-auth)"""


class AtmUser(atm_locust.MyUser):
    """ATM lookups (atm-locator)"""


class AccountUser(account_locust.MyUser):
    """account creation flow (dashboard -> accounts)"""


class TransferUser(transaction_locust.MyUser):
    """two-user money transfers (dashboard -> transactions)"""


class LoanUser(loan_locust.MyUser):
    """loan applications (dashboard -> loan)"""
