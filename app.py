import hashlib
import json
import requests
import sys, getopt
import requests
from textwrap import dedent
from time import time
from uuid import uuid4
from urllib.parse import urlparse
from ellipticcurve.ecdsa import Ecdsa
from ellipticcurve.privateKey import PrivateKey
from ellipticcurve.publicKey import PublicKey
from ellipticcurve.signature import Signature
from flask import Flask, jsonify, request, render_template

class Blockchain(object):
    def __init__(self):
        self.nodes = set()
        # 用 set 来储存节点，避免重复添加节点.
        self.chain = []
        self.current_transactions = []
        #创建创世区块
        self.new_block(previous_hash=1)

    def register_node(self,address):
        """
        在节点列表中添加一个新节点
        :param address:
        :return:
        """
        prsed_url = urlparse(address)
        self.nodes.add(prsed_url.netloc or address)
        self.nodes.discard(f'localhost:{port}')

    def valid_chain(self,chain):
        """
        确定一个给定的区块链是否有效
        :param chain:
        :return:
        """
        last_block = chain[0]
        current_index = 1

        while current_index<len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n______\n")
            # 检查block的散列是否正确
            if block['previous_hash'] != self.hash(last_block):
                return False

            last_block = block
            current_index += 1
        return True

    def resolve_conflicts(self):
        """
        共识算法
        :return:
        """
        neighbours = self.nodes
        new_chain = None
        # 寻找最长链条
        max_length = len(self.chain)

        # 获取并验证网络中的所有节点的链
        for node in neighbours:
            response = requests.get(f'http://{node}/api/chain/local')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # 检查长度是否长，链是否有效
                if length > max_length: # and self.valid_chain(chain):
                    max_length = length
                    new_chain = chain

        # 如果发现一个新的有效链比当前的长，就替换当前的链
        if new_chain:
            self.chain = new_chain
            return True
        return False

    def new_block(self,previous_hash=None):
        """
        创建一个新的块并将其添加到链中
        :param previous_hash: 前一个区块的hash值
        :return: 新区块
        """
        block = {
            'index':len(self.chain)+1,
            'timestamp':time(),
            'transactions':self.current_transactions,
            'previous_hash':previous_hash or self.hash(self.chain[-1]),
        }

        # 重置当前交易记录
        self.current_transactions = []

        self.chain.append(block)
        return block

    def new_transaction(self,sender,recipient,book_id):
        # 将新事务添加到事务列表中
        """
        Creates a new transaction to go into the next mined Block
        :param sender:发送方的地址
        :param recipient:收信人地址
        :param book_id:数量
        :return:保存该事务的块的索引
        """
        self.current_transactions.append({
            'sender':sender,
            'recipient':recipient,
            'book_id':book_id,
        })

        return self.last_block['index'] + 1

    def parse_chain(self):
        bookset = set()
        res = {}
        for block in self.chain:
            for transaction in block['transactions']:
                sender = transaction['sender']
                recipient = transaction['recipient']
                book_id = transaction['book_id']
                bookset.add(book_id)
                if recipient != "0":
                    if recipient not in res:
                        res[recipient] = []
                    res[recipient].append(book_id)
                if sender != "0":
                    res[sender].remove(book_id)
        return list(bookset), res


    @staticmethod
    def hash(block):
        """
        给一个区块生成 SHA-256 值
        :param block:
        :return:
        """
        # 必须确保这个字典（区块）是经过排序的，否则将会得到不一致的散列
        block_string = json.dumps(block,sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    @property
    def last_block(self):
        # 返回链中的最后一个块
        return self.chain[-1]

    def proof_of_work(self,last_proof):
        # 工作算法的简单证明
        proof = 0
        while self.valid_proof(last_proof,proof)is False:
            proof +=1
        return proof

    @staticmethod
    def valid_proof(last_proof,proof):
        # 验证证明
        guess =  f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        return guess_hash[:4] =="0000"


# 实例化节点
app = Flask(__name__)

block = None
port= None

# 为该节点生成一个全局惟一的地址
node_identifier = str(uuid4()).replace('-','')

# 实例化Blockchain类
blockchain = Blockchain()

# 数据加密
@app.route('/api/encoding',methods=['POST'])
def encoding():
    values = request.get_json()

    # 检查所需要的字段是否位于POST的data中
    required = ['private_key','message']
    if not all(k in values for k in required):
        return 'Missing values', 400

    privateKey = PrivateKey.fromPem(values['private_key'])
    signature = Ecdsa.sign(values['message'], privateKey)

    response = {
        'hash': signature.toBase64()
    }

    return jsonify(response), 200


# 添加图书数据
@app.route('/api/mine',methods=['POST'])
def mine():

    # 同步区块
    blockchain.resolve_conflicts()

    values = request.get_json()

    # 检查所需要的字段是否位于POST的data中
    required = ['recipient','book_id','hash']
    if not all(k in values for k in required):
        return 'Missing values', 400

    bookset, _ = blockchain.parse_chain()
    if values['book_id'] in bookset:
        return 'Book alreadt exises', 401

    publicKey = PublicKey.fromPem(values['recipient'])
    signature = Signature.fromBase64(values['hash'])

    if not Ecdsa.verify(values['book_id'], signature, publicKey):
        return 'Verified failure', 402

    last_block = blockchain.last_block

    # 写入图书
    blockchain.new_transaction(
        sender="0",
        recipient=publicKey.toPem(),
        book_id=values['book_id'],
    )

    # 通过将其添加到链中来构建新的块
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(previous_hash)
    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 200

# 创建交易请求
@app.route('/api/transactions/new',methods=['POST'])
def new_transactions():
    values = request.get_json()

    # 检查所需要的字段是否位于POST的data中
    required = ['sender','recipient','book_id', 'hash']
    if not all(k in values for k in required):
        return 'Missing values', 400

    publicKey = PublicKey.fromPem(values['sender'])
    signature = Signature.fromBase64(values['hash'])

    if not Ecdsa.verify(values['book_id'], signature, publicKey):
        return 'Verified failure', 402

    # 同步区块
    blockchain.resolve_conflicts()

    _, res = blockchain.parse_chain()
    if values['book_id'] not in res[values['sender']]:
        return 'Book not exises', 401

    #创建一个新的事物
    blockchain.new_transaction(values['sender'], values['recipient'], values['book_id'])

    last_block = blockchain.last_block

    # 通过将其添加到链中来构建新的块
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(previous_hash)
    response = {
        'message': "New Block Forged",
        'index': block['index'],
        'transactions': block['transactions'],
        'previous_hash': block['previous_hash'],
    }
    return jsonify(response), 201

# 获取解析后的数据
@app.route('/api/books',methods=['GET'])
def books():

    # 同步区块
    blockchain.resolve_conflicts()

    books, res = blockchain.parse_chain()

    response = {
        "books": books,
        "list": res
    }

    return jsonify(response), 200

# 获取链上块信息
@app.route('/api/chain',methods=['GET'])
def chain():
    
    # 同步区块
    blockchain.resolve_conflicts()

    response = {
        'chain':blockchain.chain,
        'length':len(blockchain.chain),
    }
    return jsonify(response),200

# 获取节点块信息
@app.route('/api/chain/local',methods=['GET'])
def local_chain():
    response = {
        'chain':blockchain.chain,
        'length':len(blockchain.chain),
    }
    return jsonify(response),200

# 获取节点
@app.route('/api/nodes',methods=['GET'])
def get_nodes():
    response = {
        'nodes': list(blockchain.nodes)
    }
    return jsonify(response),200

# 添加多个节点
@app.route('/api/nodes/registers',methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values['nodes']
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201

# 解决冲突
@app.route('/api/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200

# 用户注册
@app.route('/api/user/register', methods=['GET'])
def user_register():
    privateKey = PrivateKey()
    publicKey = privateKey.publicKey()

    response = {
        'message': 'User register successfully!',
        'publicKey': publicKey.toPem(),
        'privateKey': privateKey.toPem()
    }

    return jsonify(response), 200

# 加入到网络
def init_block(block_url):
    # 获取链中所有节点
    res = requests.get(f'http://{block_url}/api/nodes')

    values = json.loads(res.text)
    nodes = values.get('nodes')
    nodes.append(block_url)
    nodes.remove(f'localhost:{port}')
    
    # 本地注册+通知其他节点
    for node in nodes:
        blockchain.register_node(node)
        requests.post(f'http://{node}/api/nodes/registers',json={'nodes':[f'http://localhost:{port}']})

    blockchain.resolve_conflicts()

    return True

# 主页
@app.route('/index', methods=['GET'])
def index_page():
    return app.send_static_file('html/index.html')

# 图书
@app.route('/books', methods=['GET'])
def books_page():
    return app.send_static_file('html/books.html')

# 添加图书
@app.route('/add', methods=['GET'])
def add_page():
    return app.send_static_file('html/add.html')

# 交易
@app.route('/transaction', methods=['GET'])
def transaction_page():
    return app.send_static_file('html/transaction.html')

# 加密
@app.route('/encoding', methods=['GET'])
def encoding_page():
    return app.send_static_file('html/encoding.html')

# 注册
@app.route('/register', methods=['GET'])
def register_page():
    return app.send_static_file('html/register.html')

if __name__ == '__main__':
    block = None
    # 获取命令行参数
    try:
        opts, args = getopt.getopt(sys.argv[1:],"hp:b:")
    except getopt.GetoptError:
        print ('app.py -p <port> -b <block>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print ('app.py -p <port> -b <block>')
            sys.exit()
        elif opt == '-p':
            port = arg
        elif opt == "-b":
            block = arg

    if block and not init_block(block) or not port:
        sys.exit()
    
    app.run(host='0.0.0.0',port=port,debug=False)
