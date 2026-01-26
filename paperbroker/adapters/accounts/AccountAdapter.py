from ...accounts import Account

class AccountAdapter():

    def get_account(self, account_id:str, current_date=None):
        raise NotImplementedError("AccountAdapter.get_account: subclass me!")

    def put_account(self, account:Account, current_date=None):
        raise NotImplementedError("AccountAdapter.put_account: subclass me!")

    def get_account_ids(self, current_date=None):
        raise NotImplementedError("AccountAdapter.get_accounts: subclass me!")


