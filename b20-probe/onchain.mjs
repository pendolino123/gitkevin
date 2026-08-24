import fs from 'node:fs';
import { ethers } from 'ethers';

const USDC = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';
const NVDAC = '0xb20000000000000000000078ee7ce2fE4908108C';
const AMOUNT = 100000000n;
const ZERO = ethers.ZeroAddress;

const RPCS = [
  'https://mainnet.base.org',
  'https://base-rpc.publicnode.com',
  'https://base.llamarpc.com',
  'https://1rpc.io/base',
];

let provider;
let rpcUsed;
let lastRpcError;
for (const url of RPCS) {
  try {
    const p = new ethers.JsonRpcProvider(url, 8453, { staticNetwork: true });
    await p.getBlockNumber();
    provider = p;
    rpcUsed = url;
    break;
  } catch (e) {
    lastRpcError = e;
  }
}
if (!provider) throw lastRpcError || new Error('No Base RPC available');

function err(e) {
  return {
    name: e?.name,
    code: e?.code,
    shortMessage: e?.shortMessage,
    message: String(e?.message || e).slice(0, 1200),
    data: e?.data || e?.info?.error?.data || null,
  };
}

const erc20Abi = [
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
  'function name() view returns (string)',
  'function totalSupply() view returns (uint256)',
];
const token = new ethers.Contract(NVDAC, erc20Abi, provider);
let decimals;
const metadata = {};
for (const field of ['decimals', 'symbol', 'name', 'totalSupply']) {
  try {
    const value = await token[field]();
    metadata[field] = typeof value === 'bigint' ? value.toString() : value;
    if (field === 'decimals') decimals = Number(value);
  } catch (e) {
    metadata[field] = { error: err(e) };
  }
}

const blockNumber = await provider.getBlockNumber();
const block = await provider.getBlock(blockNumber);
const network = await provider.getNetwork();
const code = await provider.getCode(NVDAC);

const factoryAbi = ['function getPool(address tokenA,address tokenB,int24 tickSpacing) view returns (address pool)'];
const quoterAbi = [
  'function quoteExactInputSingle((address tokenIn,address tokenOut,uint256 amountIn,int24 tickSpacing,uint160 sqrtPriceLimitX96) params) returns (uint256 amountOut,uint160 sqrtPriceX96After,uint32 initializedTicksCrossed,uint256 gasEstimate)',
];

const deployments = [
  {
    generation: 'initial',
    factory: '0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A',
    quoter: '0x254cF9E1E6e233aa1AC962CB9B05b2cfeAaE15b0',
  },
  {
    generation: 'gauge-caps',
    factory: '0xaDe65c38CD4849aDBA595a4323a8C7DdfE89716a',
    quoter: '0x3d4C22254F86f64B7eC90ab8F7aeC1FBFD271c6C',
  },
  {
    generation: 'gauges-v3-current',
    factory: '0xf8f2eB4940CFE7d13603DDDD87f123820Fc061Ef',
    quoter: '0x514c8B5f54112481E28028F1166Bd78501089259',
  },
];
const tickSpacings = [1, 10, 50, 100, 200, 500, 1000, 2000];
const slipstream = [];

for (const deployment of deployments) {
  const factory = new ethers.Contract(deployment.factory, factoryAbi, provider);
  const quoter = new ethers.Contract(deployment.quoter, quoterAbi, provider);
  const row = {
    ...deployment,
    factoryCodeLength: ((await provider.getCode(deployment.factory)).length - 2) / 2,
    quoterCodeLength: ((await provider.getCode(deployment.quoter)).length - 2) / 2,
    tickSpacings: [],
  };
  for (const tickSpacing of tickSpacings) {
    const q = { tickSpacing };
    try {
      q.pool = await factory.getPool(USDC, NVDAC, tickSpacing);
    } catch (e) {
      q.poolLookupError = err(e);
    }
    if (q.pool && q.pool !== ZERO) {
      q.poolCodeLength = ((await provider.getCode(q.pool)).length - 2) / 2;
    }
    try {
      const result = await quoter.quoteExactInputSingle.staticCall({
        tokenIn: USDC,
        tokenOut: NVDAC,
        amountIn: AMOUNT,
        tickSpacing,
        sqrtPriceLimitX96: 0n,
      });
      q.amountOut = result[0].toString();
      q.amountOutFormatted = Number.isInteger(decimals) ? ethers.formatUnits(result[0], decimals) : null;
      q.sqrtPriceX96After = result[1].toString();
      q.initializedTicksCrossed = Number(result[2]);
      q.gasEstimate = result[3].toString();
    } catch (e) {
      q.quoteError = err(e);
    }
    row.tickSpacings.push(q);
  }
  slipstream.push(row);
}

const classicRouterAddress = '0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43';
const classicFactoryAddress = '0x420DD381b31aEf6683db6B902084cB0FFECe40Da';
const classicAbi = [
  'function getAmountsOut(uint256 amountIn,(address from,address to,bool stable,address factory)[] routes) view returns (uint256[] amounts)',
];
const classicRouter = new ethers.Contract(classicRouterAddress, classicAbi, provider);
const classic = {
  router: classicRouterAddress,
  factory: classicFactoryAddress,
  routerCodeLength: ((await provider.getCode(classicRouterAddress)).length - 2) / 2,
  quotes: [],
};
for (const stable of [false, true]) {
  const q = { stable };
  try {
    const amounts = await classicRouter.getAmountsOut(AMOUNT, [{
      from: USDC,
      to: NVDAC,
      stable,
      factory: classicFactoryAddress,
    }]);
    q.amounts = amounts.map((x) => x.toString());
    q.amountOut = amounts.at(-1).toString();
    q.amountOutFormatted = Number.isInteger(decimals) ? ethers.formatUnits(amounts.at(-1), decimals) : null;
  } catch (e) {
    q.error = err(e);
  }
  classic.quotes.push(q);
}

const report = {
  testedAtUtc: new Date().toISOString(),
  rpcUsed,
  chainId: network.chainId.toString(),
  blockNumber,
  blockTimestamp: block ? new Date(Number(block.timestamp) * 1000).toISOString() : null,
  pair: { tokenIn: USDC, tokenOut: NVDAC, amountIn: AMOUNT.toString() },
  nvdaToken: {
    address: NVDAC,
    codeLength: (code.length - 2) / 2,
    metadata,
  },
  slipstream,
  classic,
};

fs.mkdirSync('results', { recursive: true });
fs.writeFileSync('results/aerodrome-onchain.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify({
  testedAtUtc: report.testedAtUtc,
  rpcUsed,
  blockNumber,
  metadata,
  successfulSlipstreamQuotes: slipstream.flatMap((d) => d.tickSpacings.filter((q) => q.amountOut).map((q) => ({ generation: d.generation, tickSpacing: q.tickSpacing, pool: q.pool, amountOut: q.amountOutFormatted }))),
  successfulClassicQuotes: classic.quotes.filter((q) => q.amountOut),
}, null, 2));
