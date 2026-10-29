# 市场基准与参考数据统一入口

总清单：`manifest.json`。每项的 `file` 为相对本目录的路径，实际区间以各项 `first` / `last` 为准。这里的参考序列不计入股票样本数量。

- 14 个 ETF：SPY、QQQ、IWM、XLK、XLF、XLE、XLV、XLI、XLY、XLP、XLU、XLB、XLRE、XLC。统一读取 `<SYMBOL>/daily.json` 的 `data`；包含原始 OHLCV 及 `adj_close`。口径、区间和限制见 [README_ETF.md](README_ETF.md)。
- 其它参考序列：RSP、IVE、IVW、TLT、VIX、HYG、LQD。保留各自原交付口径和实际区间；本次目录合并不代表它们都已补齐 `adj_close`。VIX 优先文件以 manifest 中的 `file` 为准。
- HYG/LQD 来源与使用限制见 [README_HYG_LQD-1028.md](README_HYG_LQD-1028.md)。

`sources/` 保留 14 ETF 本次复权价来源快照，`adj_close_audit.json` 为对应核验。`audits/reference_etfs_20261025/` 原样保留旧目录全部四个说明、清单和审计文件；归档文件里的数据路径按本 benchmarks 目录解析，旧 README 仅作历史记录。其它历史 acceptance 文件继续保留，只代表其原核验范围。

原 `reference_etfs_20261025` 数据已合并到这里，数据文件内容与迁移前相同。顶层 `stock_data/SPY`、`stock_data/IWM` 是仍保留的旧窗口兼容导出；新的读取方统一使用本目录。
