import { useState, useEffect, useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogClose,
} from '@/components/ui/dialog'
import { apiRequest, getHyperliquidWatchlist, getBinanceWatchlist } from '@/lib/api'
import { RefreshCw, Info, CheckCircle2 } from 'lucide-react'
import ExchangeIcon from '@/components/exchange/ExchangeIcon'
import type { ExchangeId } from '@/lib/types/exchange'

const EXCHANGES: ExchangeId[] = ['hyperliquid', 'binance']
const FORWARD_PERIODS = ['1h', '4h', '12h', '24h']

function icBadge(ic: number | null | undefined) {
  if (ic == null) return <span className="text-muted-foreground">—</span>
  const abs = Math.abs(ic)
  const text = ic.toFixed(4)
  if (abs >= 0.05) return <Badge variant="default" className="bg-green-600 text-xs">{text}</Badge>
  if (abs >= 0.02) return <Badge variant="outline" className="text-yellow-500 text-xs">{text}</Badge>
  return <span className="text-muted-foreground text-xs">{text}</span>
}

function wrBadge(wr: number | null | undefined) {
  if (wr == null) return <span className="text-muted-foreground">—</span>
  const pct = (wr * 100).toFixed(1) + '%'
  if (wr >= 0.55) return <span className="text-green-500 text-sm">{pct}</span>
  if (wr >= 0.45) return <span className="text-yellow-500 text-sm">{pct}</span>
  return <span className="text-red-500 text-sm">{pct}</span>
}

interface FactorDef {
  name: string; category: string; display_name: string; display_name_zh?: string
  description: string; description_zh?: string; value_range?: string; unit?: string
}

export default function FactorLibrary() {
  const { t, i18n } = useTranslation()
  const isZh = i18n.language?.startsWith('zh')

  const [exchange, setExchange] = useState<ExchangeId>('hyperliquid')
  const [symbol, setSymbol] = useState('')
  const [symbols, setSymbols] = useState<string[]>([])
  const [period] = useState('1h')
  const [forwardPeriod, setForwardPeriod] = useState('4h')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [library, setLibrary] = useState<{ factors: FactorDef[]; categories: string[]; category_labels: any }>()
  const [values, setValues] = useState<any[]>([])
  const [effectiveness, setEffectiveness] = useState<any[]>([])
  const [lastComputeTime, setLastComputeTime] = useState<number | null>(null)
  const [computing, setComputing] = useState(false)
  const [computeDialogOpen, setComputeDialogOpen] = useState(false)
  const [computeResult, setComputeResult] = useState<any>(null)
  const [countdown, setCountdown] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiRequest('/factors/library').then(r => r.json()).then(setLibrary).catch(() => {})
  }, [])

  useEffect(() => {
    const load = async () => {
      try {
        const data = exchange === 'binance'
          ? await getBinanceWatchlist()
          : await getHyperliquidWatchlist()
        const syms = data.symbols || []
        setSymbols(syms)
        if (syms.length > 0 && !syms.includes(symbol)) setSymbol(syms[0])
      } catch { setSymbols([]) }
    }
    load()
  }, [exchange])

  const loadData = useCallback(async () => {
    if (!symbol) return
    setLoading(true)
    try {
      const [valRes, effRes, statusRes] = await Promise.all([
        apiRequest(`/factors/values?symbol=${symbol}&period=${period}&exchange=${exchange}`).then(r => r.json()).catch(() => ({ values: [] })),
        apiRequest(`/factors/effectiveness?symbol=${symbol}&period=${period}&forward_period=${forwardPeriod}&exchange=${exchange}`).then(r => r.json()).catch(() => ({ items: [] })),
        apiRequest('/factors/status').then(r => r.json()).catch(() => null),
      ])
      setValues(valRes.values || [])
      setEffectiveness(effRes.items || [])
      if (statusRes?.last_compute_time) {
        setLastComputeTime(statusRes.last_compute_time[exchange] || null)
      }
    } finally { setLoading(false) }
  }, [symbol, period, exchange, forwardPeriod])

  useEffect(() => { loadData() }, [loadData])

  useEffect(() => {
    if (!lastComputeTime) { setCountdown(''); return }
    const interval = setInterval(() => {
      const nextTs = lastComputeTime + 3600
      const remaining = Math.max(0, nextTs - Date.now() / 1000)
      if (remaining <= 0) { setCountdown('--:--'); return }
      const m = Math.floor(remaining / 60)
      const s = Math.floor(remaining % 60)
      setCountdown(`${m}:${s.toString().padStart(2, '0')}`)
    }, 1000)
    return () => clearInterval(interval)
  }, [lastComputeTime])

  const handleCompute = async () => {
    setComputeDialogOpen(true)
    setComputeResult(null)
    setComputing(true)
    try {
      const res = await apiRequest('/factors/compute', {
        method: 'POST',
        body: JSON.stringify({ exchange, period }),
      }).then(r => r.json())
      setComputeResult(res)
      await loadData()
    } catch (e: any) {
      setComputeResult({ error: e.message || 'Unknown error' })
    }
    setComputing(false)
  }

  const mergedRows = useMemo(() => {
    if (!library) return []
    const valMap = new Map(values.map(v => [v.factor_name, v]))
    const effMap = new Map(effectiveness.map(e => [e.factor_name, e]))
    const factors = categoryFilter === 'all'
      ? library.factors
      : library.factors.filter(f => f.category === categoryFilter)
    return factors.map(f => {
      const v = valMap.get(f.name)
      const e = effMap.get(f.name)
      return { ...f, value: v?.value ?? null, timestamp: v?.timestamp, ...e }
    })
  }, [library, values, effectiveness, categoryFilter])

  const categories = library?.categories || []
  const catLabels = library?.category_labels || {}
  const getCatLabel = (cat: string) => {
    const l = catLabels[cat]
    return l ? (isZh ? l.zh : l.en) : cat
  }
  const getFactorDesc = (f: FactorDef) => isZh ? (f.description_zh || f.description) : f.description
  const formatLastUpdate = () => {
    if (!lastComputeTime) return '--'
    return new Date(lastComputeTime * 1000).toLocaleString()
  }

  if (loading && !library) {
    return <div className="flex items-center justify-center h-40 text-muted-foreground">{t('factors.loading')}</div>
  }

  return (
    <TooltipProvider>
      <div className="space-y-3">
        {/* Controls row with labels */}
        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">{t('factors.exchange')}</label>
            <Select value={exchange} onValueChange={(v) => setExchange(v as ExchangeId)}>
              <SelectTrigger className="w-36">
                <div className="flex items-center gap-2">
                  <ExchangeIcon exchangeId={exchange} size={16} />
                  <span className="capitalize">{exchange}</span>
                </div>
              </SelectTrigger>
              <SelectContent>
                {EXCHANGES.map(e => (
                  <SelectItem key={e} value={e}>
                    <div className="flex items-center gap-2">
                      <ExchangeIcon exchangeId={e} size={16} />
                      <span className="capitalize">{e}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {symbols.length > 0 ? (
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">Symbol</label>
              <Select value={symbol} onValueChange={setSymbol}>
                <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {symbols.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <span className="text-sm text-muted-foreground pb-1">{t('factors.noSymbols')}</span>
          )}

          <div className="flex flex-col gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <label className="text-xs text-muted-foreground flex items-center gap-1 cursor-help">
                  {t('factors.forwardPeriodLabel')}
                  <Info className="h-3 w-3" />
                </label>
              </TooltipTrigger>
              <TooltipContent><p className="text-xs max-w-[200px]">{t('factors.forwardPeriodHint')}</p></TooltipContent>
            </Tooltip>
            <Select value={forwardPeriod} onValueChange={setForwardPeriod}>
              <SelectTrigger className="w-24"><SelectValue /></SelectTrigger>
              <SelectContent>
                {FORWARD_PERIODS.map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <Button variant="outline" size="sm" className="self-end" disabled={computing || !symbol}
            onClick={handleCompute}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${computing ? 'animate-spin' : ''}`} />
            {computing ? t('factors.computing') : t('factors.manualCompute')}
          </Button>

          <span className="text-xs text-muted-foreground ml-auto self-end pb-1">
            {t('factors.lastUpdate')}: {formatLastUpdate()}
            {countdown && ` | ${t('factors.nextCompute')}: ${countdown}`}
          </span>
        </div>

        {/* Compute progress dialog */}
        <Dialog open={computeDialogOpen} onOpenChange={setComputeDialogOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{t('factors.computeConfirmTitle')}</DialogTitle>
              <DialogDescription>{exchange} / {period}</DialogDescription>
            </DialogHeader>
            <div className="py-4">
              {computing ? (
                <div className="flex flex-col items-center gap-3">
                  <RefreshCw className="h-8 w-8 animate-spin text-primary" />
                  <p className="text-sm">{t('factors.computing')}</p>
                  <p className="text-xs text-muted-foreground">{t('factors.confirmCompute')}</p>
                </div>
              ) : computeResult?.error ? (
                <div className="text-center text-red-500 text-sm">{computeResult.error}</div>
              ) : computeResult ? (
                <div className="flex flex-col items-center gap-3">
                  <CheckCircle2 className="h-8 w-8 text-green-500" />
                  <p className="text-sm font-medium">{t('factors.computeSuccess')}</p>
                  <div className="text-xs text-muted-foreground space-y-1">
                    <p>Factor Values: {computeResult.values_computed ?? 0}</p>
                    <p>Effectiveness: {computeResult.effectiveness_computed ?? 0}</p>
                  </div>
                </div>
              ) : null}
            </div>
            {!computing && (
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="outline" size="sm">{t('common.close')}</Button>
                </DialogClose>
              </DialogFooter>
            )}
          </DialogContent>
        </Dialog>

        {/* Category filter */}
        <div className="flex gap-1.5 flex-wrap">
          <Badge variant={categoryFilter === 'all' ? 'default' : 'outline'} className="cursor-pointer text-xs"
            onClick={() => setCategoryFilter('all')}>All</Badge>
          {categories.map(c => (
            <Badge key={c} variant={categoryFilter === c ? 'default' : 'outline'}
              className="cursor-pointer text-xs" onClick={() => setCategoryFilter(c)}>
              {getCatLabel(c)}
            </Badge>
          ))}
        </div>

        {/* Data table */}
        <div className="overflow-auto max-h-[calc(100vh-240px)]">
          <Table>
            <TableHeader className="sticky top-0 bg-background z-10">
              <TableRow>
                <TableHead>{t('factors.name')}</TableHead>
                <TableHead>{t('factors.category')}</TableHead>
                <TableHead className="text-right">{t('factors.value')}</TableHead>
                <TableHead className="text-right">IC</TableHead>
                <TableHead className="text-right">ICIR</TableHead>
                <TableHead className="text-right">{t('factors.winRate')}</TableHead>
                <TableHead className="text-right">{t('factors.samples')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mergedRows.map((row: any) => (
                <TableRow key={row.name}>
                  <TableCell>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="font-medium cursor-help flex items-center gap-1">
                          {row.display_name}
                          <Info className="h-3 w-3 text-muted-foreground" />
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="right" className="max-w-xs">
                        {isZh && row.display_name_zh && (
                          <p className="text-xs font-medium mb-1">{row.display_name_zh}</p>
                        )}
                        <p className="text-xs">{getFactorDesc(row)}</p>
                        {row.value_range && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {t('factors.range')}: {row.value_range} {row.unit || ''}
                          </p>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs">{getCatLabel(row.category)}</Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {row.value != null ? row.value.toFixed(4) : '—'}
                  </TableCell>
                  <TableCell className="text-right">{icBadge(row.ic_mean)}</TableCell>
                  <TableCell className="text-right font-mono text-sm">
                    {row.icir != null ? row.icir.toFixed(2) : '—'}
                  </TableCell>
                  <TableCell className="text-right">{wrBadge(row.win_rate)}</TableCell>
                  <TableCell className="text-right text-sm">{row.sample_count ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    </TooltipProvider>
  )
}
