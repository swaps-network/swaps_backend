import datetime
import binascii
import requests
import json
import time
import hashlib
import base58

from ethereum import abi

# from tronapi import Tron
# from solc import compile_source

from django.db import models
from django.core.mail import send_mail, EmailMessage
from django.contrib.postgres.fields import JSONField
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from lastwill.contracts.submodels.common import *
from lastwill.contracts.submodels.airdrop import AirdropAddress
from lastwill.consts import NET_DECIMALS, CONTRACT_PRICE_TRON



def convert_address_to_hex(address):
    # short_addresss = address[1:]
    decode_address = base58.b58decode(address)[1:21]
    hex_address = binascii.hexlify(decode_address)
    hex_address = '0x' + hex_address.decode("utf-8")
    return hex_address


def replace_0x(message):
    for mes in message:
        mes['address'] = '41' + mes['address'][2:]
    return message


def convert_address_to_wif(address):
    short_address = '0x41' + address[2:]
    m = hashlib.sha256()
    m.update(short_address.encode())
    first_part = m.digest()
    # m.update(first_part)
    # control_sum = m.digest()
    address_with_sum = binascii.hexlify(short_address.encode() + first_part[0:4])
    # encode_address = address_with_sum.encode()
    wif_address = base58.b58encode(address_with_sum)
    return wif_address


class TRONContract(EthContract):
    pass


@contract_details('Token contract')
class ContractDetailsTRONToken(CommonDetails):
    token_name = models.CharField(max_length=512)
    token_short_name = models.CharField(max_length=64)
    admin_address = models.CharField(max_length=50)
    decimals = models.IntegerField()
    token_type = models.CharField(max_length=32, default='ERC20')
    tron_contract_token = models.ForeignKey(
        TRONContract,
        null=True,
        default=None,
        related_name='token_details',
        on_delete=models.SET_NULL
    )
    future_minting = models.BooleanField(default=False)
    temp_directory = models.CharField(max_length=36)

    def predeploy_validate(self):
        now = timezone.now()
        token_holders = self.contract.tokenholder_set.all()
        for th in token_holders:
            if th.freeze_date:
                if th.freeze_date < now.timestamp() + 600:
                    raise ValidationError({'result': 1}, code=400)

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(CONTRACT_PRICE_TRON['TRON_TOKEN'] * NET_DECIMALS['ETH'])
        return result

    def get_arguments(self, eth_contract_attr_name):
        return []

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('standalone token contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(self, sour_path='lastwill/tron-token/*')
        token_holders = self.contract.tokenholder_set.all()
        for th in token_holders:
            if th.address.startswith('41'):
                th.address = '0x' + th.address[2:]
                th.save()
            else:
                th.address = convert_address_to_hex(th.address)
                th.save()
        preproc_params = {"constants": {"D_ONLY_TOKEN": True}}
        preproc_params['constants'] = add_token_params(
            preproc_params['constants'], self, token_holders,
            False, self.future_minting
        )
        owner = '0x' + self.admin_address[2:] if self.admin_address.startswith('41') else convert_address_to_hex(self.admin_address)
        preproc_params['constants']['D_CONTRACTS_OWNER'] = owner
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && yarn compile'.format(dest=dest)):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/MainToken.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/MainToken.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        tron_contract_token = TRONContract()
        tron_contract_token.abi = token_json['abi']
        tron_contract_token.bytecode = token_json['bytecode'][2:]
        tron_contract_token.compiler_version = token_json['compiler']['version']
        tron_contract_token.contract = self.contract
        tron_contract_token.original_contract = self.contract
        tron_contract_token.source_code = source_code
        tron_contract_token.save()
        self.tron_contract_token = tron_contract_token
        self.save()
        token_holders = self.contract.tokenholder_set.all()
        for th in token_holders:
            if th.address.startswith('0x'):
                th.address = '41' + th.address[2:]
                th.save()

    @blocking
    @postponable
    def deploy(self, eth_contract_attr_name='eth_contract_token'):
        self.compile()
        print('deploy tron token')
        abi = json.dumps(self.tron_contract_token.abi)
        deploy_params = {
            'abi': str(abi),
            'bytecode': self.tron_contract_token.bytecode,
            'consume_user_resource_percent': 0,
            'fee_limit': 1000000000,
            'call_value': 0,
            'bandwidth_limit': 1000000,
            'owner_address': '41' + convert_address_to_hex(NETWORKS[self.contract.network.name]['address'])[2:],
            'origin_energy_limit': 100000000
        }
        deploy_params = json.dumps(deploy_params)
        tron_url = 'http://%s:%s' % (str(NETWORKS[self.contract.network.name]['host']), str(NETWORKS[self.contract.network.name]['port']))
        result = requests.post(tron_url + '/wallet/deploycontract', data=deploy_params)
        print('transaction created')
        trx_info1 = json.loads(result.content.decode())
        trx_info1 = {'transaction': trx_info1}
        # print('trx info', trx_info1)
        self.tron_contract_token.address = trx_info1['transaction']['contract_address']
        self.tron_contract_token.save()
        trx_info1['privateKey'] = NETWORKS[self.contract.network.name]['private_key']
        trx = json.dumps(trx_info1)
        # print('before', trx)
        result = requests.post(tron_url + '/wallet/gettransactionsign', data=trx)
        print('transaction sign')
        trx_info2 = json.loads(result.content.decode())
        trx = json.dumps(trx_info2)
        # print('after', trx)
        # print(trx)
        for i in range(5):
            print('attempt=', i)
            result = requests.post(tron_url + '/wallet/broadcasttransaction', data=trx)
            print(result.content)
            answer = json.loads(result.content.decode())
            print('answer=', answer, flush=True)
            if answer['result']:
                params = {'value': trx_info2['txID']}
                result = requests.post(tron_url + '/wallet/gettransactionbyid', data=json.dumps(params))
                ret = json.loads(result.content.decode())
                if ret:
                    self.tron_contract_token.tx_hash = trx_info2['txID']
                    print('tx_hash=', trx_info2['txID'], flush=True)
                    self.tron_contract_token.save()
                    self.contract.state = 'WAITING_FOR_DEPLOYMENT'
                    self.contract.save()
                    return
            time.sleep(5)
        else:
                raise ValidationError({'result': 1}, code=400)

    def msg_deployed(self, message, eth_contract_attr_name='eth_contract'):
        self.contract.state = 'ACTIVE'
        self.contract.save()
        take_off_blocking(self.contract.network.name)

    def ownershipTransferred(self, message):
        if self.tron_contract_token.original_contract.state not in (
                'UNDER_CROWDSALE', 'ENDED'
        ):
            self.tron_contract_token.original_contract.state = 'UNDER_CROWDSALE'
            self.tron_contract_token.original_contract.save()

    def finalized(self, message):
        if self.tron_contract_token.original_contract.state != 'ENDED':
            self.tron_contract_token.original_contract.state = 'ENDED'
            self.tron_contract_token.original_contract.save()
        if (self.tron_contract_token.original_contract.id !=
                self.tron_contract_token.contract.id and
                self.tron_contract_token.contract.state != 'ENDED'):
            self.tron_contract_token.contract.state = 'ENDED'
            self.tron_contract_token.contract.save()

    def check_contract(self):
        pass

    def initialized(self, message):
        pass


@contract_details('Game Asset contract')
class ContractDetailsGameAssets(CommonDetails):
    token_name = models.CharField(max_length=512)
    token_short_name = models.CharField(max_length=64)
    admin_address = models.CharField(max_length=50)
    temp_directory = models.CharField(max_length=36)
    uri = models.CharField(max_length=2000)
    tron_contract_token = models.ForeignKey(
        TRONContract,
        null=True,
        default=None,
        related_name='game_asset_details',
        on_delete=models.SET_NULL
    )

    def predeploy_validate(self):
        pass

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(CONTRACT_PRICE_TRON['TRON_GAME_ASSET'] * NET_DECIMALS['ETH'])
        return result

    def get_arguments(self, eth_contract_attr_name):
        return []

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('standalone token contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(self, sour_path='lastwill/game-assets-contract/*')
        owner = '0x' + self.admin_address[2:] if self.admin_address.startswith('41') else convert_address_to_hex(self.admin_address)
        preproc_params = {"constants":
            {
                "D_NAME": self.token_name,
                "D_SYMBOL": self.token_short_name,
                "D_OWNER": owner,
                "D_URI": self.uri
            }
}
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && yarn compile'.format(dest=dest)):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/GameAssetsContract.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/GameAssetsContract.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        tron_contract_token = TRONContract()
        tron_contract_token.abi = token_json['abi']
        tron_contract_token.bytecode = token_json['bytecode'][2:]
        tron_contract_token.compiler_version = token_json['compiler']['version']
        tron_contract_token.contract = self.contract
        tron_contract_token.original_contract = self.contract
        tron_contract_token.source_code = source_code
        tron_contract_token.save()
        self.tron_contract_token = tron_contract_token
        self.save()

    @blocking
    @postponable
    def deploy(self, eth_contract_attr_name='eth_contract_token'):
        self.compile()
        print('deploy tron token')
        abi = json.dumps(self.tron_contract_token.abi)
        deploy_params = {
            'abi': str(abi),
            'bytecode': self.tron_contract_token.bytecode,
            'consume_user_resource_percent': 0,
            'fee_limit': 1000000000,
            'call_value': 0,
            'bandwidth_limit': 1000000,
            'owner_address': '41' + convert_address_to_hex(NETWORKS[self.contract.network.name]['address'])[2:],
            'origin_energy_limit': 100000000
        }
        deploy_params = json.dumps(deploy_params)
        tron_url = 'http://%s:%s' % (str(NETWORKS[self.contract.network.name]['host']), str(NETWORKS[self.contract.network.name]['port']))
        result = requests.post(tron_url + '/wallet/deploycontract', data=deploy_params)
        print('transaction created')
        trx_info1 = json.loads(result.content.decode())
        trx_info1 = {'transaction': trx_info1}
        # print('trx info', trx_info1)
        self.tron_contract_token.address = trx_info1['transaction']['contract_address']
        self.tron_contract_token.save()
        trx_info1['privateKey'] = NETWORKS[self.contract.network.name]['private_key']
        trx = json.dumps(trx_info1)
        # print('before', trx)
        result = requests.post(tron_url + '/wallet/gettransactionsign', data=trx)
        print('transaction sign')
        trx_info2 = json.loads(result.content.decode())
        trx = json.dumps(trx_info2)
        # print('after', trx)
        # print(trx)
        for i in range(5):
            print('attempt=', i)
            result = requests.post(tron_url + '/wallet/broadcasttransaction', data=trx)
            print(result.content)
            answer = json.loads(result.content.decode())
            print('answer=', answer, flush=True)
            if answer['result']:
                params = {'value': trx_info2['txID']}
                result = requests.post(tron_url + '/wallet/gettransactionbyid', data=json.dumps(params))
                ret = json.loads(result.content.decode())
                if ret:
                    self.tron_contract_token.tx_hash = trx_info2['txID']
                    print('tx_hash=', trx_info2['txID'], flush=True)
                    self.tron_contract_token.save()
                    self.contract.state = 'WAITING_FOR_DEPLOYMENT'
                    self.contract.save()
                    return
            time.sleep(5)
        else:
                raise ValidationError({'result': 1}, code=400)

    def msg_deployed(self, message, eth_contract_attr_name='eth_contract'):
        self.contract.state = 'ACTIVE'
        self.contract.save()
        take_off_blocking(self.contract.network.name)

    def ownershipTransferred(self, message):
        if self.tron_contract_token.original_contract.state not in (
                'UNDER_CROWDSALE', 'ENDED'
        ):
            self.tron_contract_token.original_contract.state = 'UNDER_CROWDSALE'
            self.tron_contract_token.original_contract.save()

    def finalized(self, message):
        if self.tron_contract_token.original_contract.state != 'ENDED':
            self.tron_contract_token.original_contract.state = 'ENDED'
            self.tron_contract_token.original_contract.save()
        if (self.tron_contract_token.original_contract.id !=
                self.tron_contract_token.contract.id and
                self.tron_contract_token.contract.state != 'ENDED'):
            self.tron_contract_token.contract.state = 'ENDED'
            self.tron_contract_token.contract.save()

    def check_contract(self):
        pass

    def initialized(self, message):
        pass


@contract_details('Tron Airdrop contract')
class ContractDetailsTRONAirdrop(CommonDetails):
    contract = models.ForeignKey(Contract, null=True)
    admin_address = models.CharField(max_length=50)
    token_address = models.CharField(max_length=50)
    temp_directory = models.CharField(max_length=36)
    tron_contract = models.ForeignKey(
        TRONContract,
        null=True,
        default=None,
        related_name='tron_airdrop_details',
        on_delete=models.SET_NULL
    )

    def get_arguments(self, *args, **kwargs):
        return [
            self.admin_address,
            self.token_address
        ]

    def predeploy_validate(self):
        pass

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(0.5 * 10 ** 18)
        return result

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('standalone token contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(self, sour_path='lastwill/tron-airdrop-contract/*')
        owner = '0x' + self.admin_address[2:] if self.admin_address.startswith('41') else convert_address_to_hex(self.admin_address)
        token = '0x' + self.token_address[2:] if self.token_address.startswith('41') else convert_address_to_hex(self.token_address)
        preproc_params = {"constants": {"D_TOKEN": token, "D_TARGET": owner}}
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && yarn compile'.format(dest=dest)):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/AirDrop.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/AirDrop.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        tron_contract = TRONContract()
        tron_contract.abi = token_json['abi']
        tron_contract.bytecode = token_json['bytecode'][2:]
        tron_contract.compiler_version = token_json['compiler']['version']
        tron_contract.contract = self.contract
        tron_contract.original_contract = self.contract
        tron_contract.source_code = source_code
        tron_contract.save()
        self.tron_contract = tron_contract
        self.save()

    @blocking
    @postponable
    def deploy(self, eth_contract_attr_name='eth_contract_token'):
        self.compile()
        print('deploy tron token')
        abi = json.dumps(self.tron_contract.abi)
        deploy_params = {
            'abi': str(abi),
            'bytecode': self.tron_contract.bytecode,
            'consume_user_resource_percent': 0,
            'fee_limit': 1000000000,
            'call_value': 0,
            'bandwidth_limit': 1000000,
            'owner_address': '41' + convert_address_to_hex(NETWORKS[self.contract.network.name]['address'])[2:],
            'origin_energy_limit': 100000000
        }
        deploy_params = json.dumps(deploy_params)
        tron_url = 'http://%s:%s' % (str(NETWORKS[self.contract.network.name]['host']), str(NETWORKS[self.contract.network.name]['port']))
        result = requests.post(tron_url + '/wallet/deploycontract', data=deploy_params)
        print('transaction created')
        trx_info1 = json.loads(result.content.decode())
        trx_info1 = {'transaction': trx_info1}
        # print('trx info', trx_info1)
        self.tron_contract.address = trx_info1['transaction']['contract_address']
        self.tron_contract.save()
        trx_info1['privateKey'] = NETWORKS[self.contract.network.name]['private_key']
        trx = json.dumps(trx_info1)
        # print('before', trx)
        result = requests.post(tron_url + '/wallet/gettransactionsign', data=trx)
        print('transaction sign')
        trx_info2 = json.loads(result.content.decode())
        trx = json.dumps(trx_info2)
        # print('after', trx)
        # print(trx)
        for i in range(5):
            print('attempt=', i)
            result = requests.post(tron_url + '/wallet/broadcasttransaction', data=trx)
            print(result.content)
            answer = json.loads(result.content.decode())
            print('answer=', answer, flush=True)
            if answer['result']:
                params = {'value': trx_info2['txID']}
                result = requests.post(tron_url + '/wallet/gettransactionbyid', data=json.dumps(params))
                ret = json.loads(result.content.decode())
                if ret:
                    self.tron_contract.tx_hash = trx_info2['txID']
                    print('tx_hash=', trx_info2['txID'], flush=True)
                    self.tron_contract.save()
                    self.contract.state = 'WAITING_FOR_DEPLOYMENT'
                    self.contract.save()
                    return
            time.sleep(5)
        else:
                raise ValidationError({'result': 1}, code=400)

    def airdrop(self, message):
        message['airdroppedAddresses'] = replace_0x(message['airdroppedAddresses'])
        new_state = {
            'COMMITTED': 'sent',
            'PENDING': 'processing',
            'REJECTED': 'added'
        }[message['status']]
        old_state = {
            'COMMITTED': 'processing',
            'PENDING': 'added',
            'REJECTED': 'processing'
        }[message['status']]

        ids = []
        for js in message['airdroppedAddresses']:
            address = js['address']
            amount = js['value']
            addr = AirdropAddress.objects.filter(
                address=address,
                amount=amount,
                contract=self.contract,
                active=True,
                state=old_state,
            ).exclude(id__in=ids).first()
            # in case 'pending' msg was lost or dropped, but 'commited' is there
            if addr is None and message['status'] == 'COMMITTED':
                old_state = 'added'
                addr = AirdropAddress.objects.filter(
                    address=address,
                    amount=amount,
                    contract=self.contract,
                    active=True,
                    state=old_state
                ).exclude(id__in=ids).first()
            if addr is None:
                continue

            ids.append(addr.id)

        if len(message['airdroppedAddresses']) != len(ids):
            print('=' * 40, len(message['airdroppedAddresses']), len(ids),
                  flush=True)
        AirdropAddress.objects.filter(id__in=ids).update(state=new_state)
        if self.contract.airdropaddress_set.filter(state__in=('added', 'processing'),
                                              active=True).count() == 0:
            self.contract.state = 'ENDED'
            self.contract.save()

    def msg_deployed(self, message, eth_contract_attr_name='eth_contract'):
        self.contract.state = 'ACTIVE'
        self.contract.save()
        take_off_blocking(self.contract.network.name)

@contract_details('Tron Lost key contract')
class ContractDetailsTRONLostKey(CommonDetails):
    sol_path = 'lastwill/lost-key/'
    source_filename = 'contracts/LostKeyDelayedPaymentWallet.sol'
    result_filename = 'build/contracts/LostKeyDelayedPaymentWallet.json'
    user_address = models.CharField(max_length=50, null=True, default=None)
    check_interval = models.IntegerField()
    active_to = models.DateTimeField()
    last_check = models.DateTimeField(null=True, default=None)
    next_check = models.DateTimeField(null=True, default=None)
    eth_contract = models.ForeignKey(EthContract, null=True, default=None)
    transfer_threshold_wei = models.IntegerField(default=0)
    transfer_delay_seconds = models.IntegerField(default=0)

    def predeploy_validate(self):
        now = timezone.now()
        if self.active_to < now:
            raise ValidationError({'result': 1}, code=400)

    def get_arguments(self, *args, **kwargs):
        return [
            self.user_address,
            [h.address for h in self.contract.heir_set.all()],
            [h.percentage for h in self.contract.heir_set.all()],
            self.check_interval,
#            self.transfer_threshold_wei,
#            self.transfer_delay_seconds
            2**256-1,
            0,
        ]

    def fundsAdded(self, message):
        pass

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='ETHEREUM_MAINNET')
        now = datetime.datetime.now()
        cost = cls.calc_cost({
            'check_interval': 1,
            'heirs': [],
            'active_to': now
        }, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        heirs_num = int(kwargs['heirs_num']) if 'heirs_num' in kwargs else len(
            kwargs['heirs'])
        active_to = kwargs['active_to']
        if isinstance(active_to, str):
            if 'T' in active_to:
                active_to = active_to[:active_to.index('T')]
            active_to = datetime.date(*map(int, active_to.split('-')))
        elif isinstance(active_to, datetime.datetime):
            active_to = active_to.date()
        check_interval = int(kwargs['check_interval'])
        Cg = 1476117
        CBg = 28031
        Tg = 22000
        Gp = 60 * NET_DECIMALS['ETH_GAS_PRICE']
        Dg = 29435
        DBg = 9646
        B = heirs_num
        Cc = 124852
        DxC = max(abs((
                                  datetime.date.today() - active_to).total_seconds() / check_interval),
                  1)
        O = 25000 * NET_DECIMALS['ETH_GAS_PRICE']
        return 2 * int(
            Tg * Gp + Gp * (Cg + B * CBg) + Gp * (Dg + DBg * B) + (
                        Gp * Cc + O) * DxC
        ) + 80000

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        super().msg_deployed(message)
        self.next_check = timezone.now() + datetime.timedelta(
            seconds=self.check_interval)
        self.save()

    @check_transaction
    def checked(self, message):
        now = timezone.now()
        self.last_check = now
        next_check = now + datetime.timedelta(seconds=self.check_interval)
        if next_check < self.active_to:
            self.next_check = next_check
        else:
            self.contract.state = 'EXPIRED'
            self.contract.save()
            self.next_check = None
        self.save()
        take_off_blocking(self.contract.network.name, self.contract.id)

    @check_transaction
    def triggered(self, message):
        self.last_check = timezone.now()
        self.next_check = None
        self.save()
        heirs = Heir.objects.filter(contract=self.contract)
        link = NETWORKS[self.eth_contract.contract.network.name]['link_tx']
        for heir in heirs:
            if heir.email:
                send_mail(
                    heir_subject,
                    heir_message.format(
                        user_address=heir.address,
                        link_tx=link.format(tx=message['transactionHash'])
                    ),
                    DEFAULT_FROM_EMAIL,
                    [heir.email]
                )
        self.contract.state = 'TRIGGERED'
        self.contract.save()
        if self.contract.user.email:
            send_mail(
                carry_out_subject,
                carry_out_message,
                DEFAULT_FROM_EMAIL,
                [self.contract.user.email]
            )

    def get_gaslimit(self):
        Cg = 3200000
        CBg = 28031
        return Cg + len(self.contract.heir_set.all()) * CBg

    @blocking
    @postponable
    def deploy(self):
        return super().deploy()