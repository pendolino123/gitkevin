import fs from 'node:fs';
import { ethers } from 'ethers';

const USDC = '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';
const NVDAC = '0xb20000000000000000000078ee7ce2fE4908108C';
const QUOTER = '0x514c8B5f54112481E28028F1166Bd78501089259';
const POOL = '0x853F5f1B92b16714Fe6CDA67CAad0856B83C7ab9';
const TICK_SPACING = 10;
const RPCS = ['https://mainnet.base.org','https://base-rpc.publicnode.com','https://base.llamarpc.com','https://1rpc.io/base'];
let provider, rpcUsed;
for (const url of RPCS) {
  try {
    const p = new ethers.JsonRpcProvider(url, 8453, { staticNetwork: true });
    await p.getBlockNumber(); provider=p; rpcUsed=url; break;
  } catch {}
}
if (!provider) throw new Error('No Base RPC');
const iface = new ethers.Interface([
  'function quoteExactInputSingle((address tokenIn,address tokenOut,uint256 amountIn,int24 tickSpacing,uint160 sqrtPriceLimitX96) params) returns (uint256 amountOut,uint160 sqrtPriceX96After,uint32 initializedTicksCrossed,uint256 gasEstimate)',
]);

async function quote(amountIn, blockTag='latest') {
  const data = iface.encodeFunctionData('quoteExactInputSingle', [{tokenIn:USDC,tokenOut:NVDAC,amountIn,tickSpacing:TICK_SPACING,sqrtPriceLimitX96:0n}]);
  const raw = await provider.call({to: QUOTER, data, blockTag});
  const d = iface.decodeFunctionResult('quoteExactInputSingle', raw);
  return {amountIn:amountIn.toString(), amountOut:d[0].toString(), amountOutFormatted:ethers.formatUnits(d[0],8), sqrtPriceX96After:d[1].toString(), initializedTicksCrossed:Number(d[2]), gasEstimate:d[3].toString(), blockTag};
}

const currentBlock = await provider.getBlockNumber();
const tags = [50410444, 50410453, currentBlock];
const amounts = [100000000n, 99750000n, 99500000n];
const quotes=[];
for (const blockTag of tags) {
  for (const amount of amounts) {
    try { quotes.push(await quote(amount, blockTag)); }
    catch(e) { quotes.push({amountIn:amount.toString(), blockTag, error:{code:e.code, shortMessage:e.shortMessage, message:String(e.message).slice(0,700)}}); }
  }
}
const report={testedAtUtc:new Date().toISOString(),rpcUsed,currentBlock,quoter:QUOTER,pool:POOL,tickSpacing:TICK_SPACING,quotes};
fs.mkdirSync('results',{recursive:true});
fs.writeFileSync('results/aerodrome-benchmark.json',JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));
