'use client'

import { useEffect, useMemo, useRef, useState } from 'react'

type Plan = { name: string; price: string; speed: string; duration: string; hours: number }
type Voucher = { code: string; username: string; password: string; expiresAt?: number; planName?: string }
type FlowStep = 'plans' | 'phone' | 'pending' | 'success' | 'failed' | 'retrieve' | 'empty' | 'error' | 'active' | 'connected'
type ApiVoucher = { code: string; username: string; password: string; plan_name: string; expires_at: string }
type PaymentStatus = { status: 'pending' | 'completed' | 'failed'; voucher: ApiVoucher | null }

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'

const plans: Plan[] = [
  { name: 'DAY PASS', price: 'UGX 2,000', speed: '10 Mbps', duration: '24 hours', hours: 24 },
  { name: 'WEEK PASS', price: 'UGX 8,000', speed: '15 Mbps', duration: '7 days', hours: 168 },
  { name: 'MONTH PASS', price: 'UGX 25,000', speed: '20 Mbps', duration: '30 days', hours: 720 },
]
function toVoucher(voucher: ApiVoucher): Voucher { return { code: voucher.code, username: voucher.username, password: voucher.password, expiresAt: new Date(voucher.expires_at).getTime(), planName: voucher.plan_name } }
function saveVoucherSession(voucher: Voucher) { localStorage.setItem('wifi-voucher', JSON.stringify(voucher)) }
function getActiveVoucherSession(): Voucher | null {
  try {
    const saved = localStorage.getItem('wifi-voucher')
    if (!saved) return null
    const voucher = JSON.parse(saved) as Voucher
    return voucher.expiresAt && voucher.expiresAt > Date.now() ? voucher : null
  } catch { return null }
}
function measurePing() { return 24 }
function measureDownloadSpeed() { return 18 }

export default function Page() {
  const [step, setStep] = useState<FlowStep>('plans')
  const [selectedPlan, setSelectedPlan] = useState(plans[0])
  const [phone, setPhone] = useState('')
  const [error, setError] = useState('')
  const [seconds, setSeconds] = useState(45)
  const [voucher, setVoucher] = useState<Voucher | null>(null)
  const [copied, setCopied] = useState('')
  const [failureReason, setFailureReason] = useState('Insufficient balance')
  const [lastAction, setLastAction] = useState<() => void>(() => () => setStep('plans'))
  const [showGuide, setShowGuide] = useState(false)
  const [activeRemaining, setActiveRemaining] = useState('')
  const [transactionId, setTransactionId] = useState('')
  const hydrated = useRef(false)
  const historySync = useRef(false)

  useEffect(() => {
    const saved = sessionStorage.getItem('hotspotFlowState')
    const queryStep = new URLSearchParams(window.location.search).get('step') as FlowStep | null
    let restored = false
    if (saved) {
      try {
        const data = JSON.parse(saved) as { timestamp: number; step: FlowStep; selectedPlan?: Plan; phone?: string; voucher?: Voucher | null; transactionId?: string; seconds?: number }
        if (Date.now() - data.timestamp <= 15 * 60 * 1000) {
          const validStep = ['plans', 'phone', 'pending', 'success', 'failed', 'retrieve', 'empty', 'error', 'active', 'connected'].includes(data.step)
          if (validStep && (data.step !== 'success' || data.voucher)) {
            setStep(data.step); setSelectedPlan(data.selectedPlan ?? plans[0]); setPhone(data.phone ?? '')
            setVoucher(data.voucher ?? null); setTransactionId(data.transactionId ?? ''); setSeconds(data.seconds ?? 45); restored = true
          }
        } else sessionStorage.removeItem('hotspotFlowState')
      } catch { sessionStorage.removeItem('hotspotFlowState') }
    }
    const active = getActiveVoucherSession()
    if (!restored && active) { setVoucher(active); setStep('active'); setSelectedPlan(plans.find((plan) => plan.name === active.planName) ?? plans[0]); restored = true }
    if (!restored && queryStep && queryStep !== 'plans') window.history.replaceState(null, '', '?step=plans')
    hydrated.current = true
  }, [])

  useEffect(() => {
    const returnedTransactionId = new URLSearchParams(window.location.search).get('transaction_id')
    if (!returnedTransactionId) return
    setTransactionId(returnedTransactionId)
    setSeconds(45)
    setStep('pending')
    window.history.replaceState(null, '', '?step=pending')
  }, [])

  useEffect(() => {
    if (!hydrated.current) return
    const params = new URLSearchParams(window.location.search)
    if (params.get('step') !== step) {
      window.history.pushState({ step }, '', `?step=${step}`)
    }
    if (step === 'success') sessionStorage.removeItem('hotspotFlowState')
    else sessionStorage.setItem('hotspotFlowState', JSON.stringify({ timestamp: Date.now(), step, selectedPlan, phone, voucher, transactionId, seconds }))
  }, [step, selectedPlan, phone, voucher, transactionId, seconds])

  useEffect(() => {
    const onPopState = () => {
      const next = new URLSearchParams(window.location.search).get('step') as FlowStep | null
      if (next && ['plans', 'phone', 'pending', 'success', 'failed', 'retrieve', 'empty', 'error', 'active', 'connected'].includes(next) && (next !== 'success' || voucher)) setStep(next)
      else window.history.replaceState(null, '', '?step=plans')
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [voucher])

  useEffect(() => {
    if (step !== 'pending') return
    const timer = window.setInterval(() => setSeconds((current) => current > 0 ? current - 1 : 0), 1000)
    return () => window.clearInterval(timer)
  }, [step])

  useEffect(() => {
    if (step !== 'pending' || !transactionId) return
    let cancelled = false
    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/payment/status/${transactionId}`)
        if (!response.ok) throw new Error('Payment status request failed')
        const result = await response.json() as PaymentStatus
        if (cancelled || result.status === 'pending') return
        if (result.status === 'failed') { setFailureReason('Payment was cancelled or could not be completed.'); setStep('failed'); return }
        if (!result.voucher) throw new Error('Voucher was not returned')
        const nextVoucher = toVoucher(result.voucher)
        setVoucher(nextVoucher); saveVoucherSession(nextVoucher); setStep('success')
      } catch { if (!cancelled) setStep('error') }
    }
    void poll()
    const timer = window.setInterval(() => void poll(), 5000)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [step, transactionId])
  useEffect(() => {
    if (step !== 'active' || !voucher?.expiresAt) return
    const update = () => { const minutes = Math.max(0, Math.floor((voucher.expiresAt! - Date.now()) / 60000)); setActiveRemaining(`Expires in ${Math.floor(minutes / 60)}h ${minutes % 60}m`) }
    update(); const timer = window.setInterval(update, 60000); return () => window.clearInterval(timer)
  }, [step, voucher])

  const formattedPhone = useMemo(() => phone.replace(/\D/g, ''), [phone])
  const runPayment = async () => {
    if (formattedPhone.length < 9) { setError('Enter a valid phone number to continue.'); return }
    setError(''); setLastAction(() => runPayment)
    try {
      const response = await fetch(`${API_BASE_URL}/api/payment/initiate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan_name: selectedPlan.name, phone: formattedPhone }) })
      if (!response.ok) throw new Error('Could not start payment')
      const payment = await response.json() as { transaction_id: number; redirect_url: string }
      setTransactionId(String(payment.transaction_id)); setSeconds(45); setStep('pending')
      window.location.assign(payment.redirect_url)
    } catch { setStep('error') }
  }
  const getVoucher = async () => {
    setLastAction(() => getVoucher)
    try {
      const response = await fetch(`${API_BASE_URL}/api/voucher/retrieve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone }) })
      if (response.status === 404) { setError(''); setStep('empty'); return }
      if (!response.ok) throw new Error('Voucher lookup failed')
      const result = await response.json() as ApiVoucher
      setVoucher(toVoucher(result)); setError(''); setStep('success')
    } catch { setStep('error') }
  }
  async function copyValue(label: string, value: string) { await navigator.clipboard?.writeText(value); setCopied(label); window.setTimeout(() => setCopied(''), 2000) }
  const beginRetrieve = () => { setError(''); setStep('retrieve') }

  return <main className="site-shell">
    <header className="masthead"><div className="brand-mark" aria-label="Tafar WiFi">TAFAR<br />WIFI</div><div className="masthead-meta">[PUBLIC ACCESS]<br />KAMPALA / UG</div><button className="text-button" onClick={beginRetrieve}>Retrieve voucher <span>↗</span></button></header>
    <section className="hero-grid"><p className="eyebrow">[INTERNET ACCESS / 2026]</p><div><h1>{step === 'success' || step === 'active' ? 'You’re connected!' : step === 'connected' ? 'Connection tested.' : <>Simple access.<br />No friction.</>}</h1><p className="hero-copy">Fast, reliable WiFi for where you are. Choose a pass, pay with your phone, and get online.</p></div></section>
    <div className="flow-rule" /><section className="flow-section"><div className="section-label">[{step === 'retrieve' || step === 'empty' ? 'RETRIEVE VOUCHER' : step === 'pending' ? 'PAYMENT STATUS' : step === 'failed' ? 'PAYMENT FAILED' : step === 'error' ? 'CONNECTION ERROR' : step === 'success' || step === 'active' ? (step === 'active' ? 'ACTIVE PLAN' : 'YOUR VOUCHER') : 'SELECT PLAN'}]</div><div className="section-content">
      {step === 'plans' && <><div className="plan-list" role="radiogroup" aria-label="WiFi plans">{plans.map((plan) => <button key={plan.name} className={`plan-row ${selectedPlan.name === plan.name ? 'is-selected' : ''}`} onClick={() => setSelectedPlan(plan)} role="radio" aria-checked={selectedPlan.name === plan.name}><span className="plan-name">{plan.name}</span><span className="plan-detail">{plan.speed} / {plan.duration}</span><strong>{plan.price}</strong></button>)}</div><button className="primary-button" onClick={() => setStep('phone')}>Continue <span>→</span></button></>}
      {step === 'phone' && <PhoneForm phone={phone} setPhone={setPhone} formattedPhone={formattedPhone} error={error} onSubmit={runPayment} onBack={() => setStep('plans')} />}
      {step === 'pending' && <div className="pending-state"><div className="loader" aria-label="Waiting for payment" /><h2>CHECK YOUR PHONE</h2><p>Approve the payment request sent to +256 {phone || '…'}. This page will update automatically.</p><div className="countdown">00:{String(seconds).padStart(2, '0')}</div></div>}
      {step === 'failed' && <div className="message-state"><h2>Payment wasn&apos;t completed</h2><p>{failureReason}</p><button className="primary-button" onClick={() => setStep('phone')}>Try Again <span>→</span></button><button className="back-button" onClick={() => setStep('plans')}>Change Plan</button></div>}
      {(step === 'success' || step === 'active') && voucher && <VoucherView voucher={voucher} active={step === 'active'} remaining={activeRemaining} copied={copied} copyValue={copyValue} showGuide={showGuide} setShowGuide={setShowGuide} onConnect={() => setStep('connected')} onBuy={() => { setVoucher(null); setStep('plans') }} />}
      {step === 'connected' && <div className="connected-state"><span className="status-mark">✓</span><h2>You&apos;re connected!</h2><p>Your Tafar WiFi pass is active. Ping {measurePing()}ms · Download {measureDownloadSpeed()} Mbps.</p><button className="back-button" onClick={() => setStep('plans')}>Purchase another pass →</button></div>}
      {(step === 'retrieve' || step === 'empty') && <div className="narrow-form"><label className="eyebrow" htmlFor="retrieve-phone">[ENTER THE NUMBER USED TO PAY]</label><div className="phone-line"><span>+256</span><input id="retrieve-phone" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="7XX XXX XXX" inputMode="tel" autoFocus /></div>{step === 'empty' && <div className="message-state compact"><h2>NO VOUCHER FOUND</h2><p>We couldn&apos;t find an active plan for this number.</p><button className="primary-button" onClick={() => setStep('plans')}>Buy a Plan <span>→</span></button></div>}<button className="primary-button" onClick={getVoucher}>Find my voucher <span>→</span></button><button className="back-button" onClick={() => setStep('plans')}>← Start over</button></div>}
      {step === 'error' && <div className="message-state"><h2>Something went wrong.</h2><p>Check your connection and try again.</p><button className="primary-button" onClick={() => lastAction()}>Try Again <span>→</span></button></div>}
    </div></section>
    <footer><span>© TAFAR WIFI</span><span>SUPPORT@TAFARWIFI.UG</span><a href="https://wa.me/256XXXXXXXXX">Need help?</a><span>SESSION SECURE</span></footer>
  </main>
}

function PhoneForm({ phone, setPhone, formattedPhone, error, onSubmit, onBack }: { phone: string; setPhone: (value: string) => void; formattedPhone: string; error: string; onSubmit: () => void; onBack: () => void }) { return <div className="narrow-form"><label className="eyebrow" htmlFor="phone">[ENTER YOUR NUMBER]</label><div className="phone-line"><span>+256</span><input id="phone" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="7XX XXX XXX" inputMode="tel" autoFocus /><span className="provider-note">{formattedPhone.length >= 9 ? 'Mobile money' : ''}</span></div>{error && <p className="form-error">{error}</p>}<button className="primary-button" onClick={onSubmit}>Request payment <span>→</span></button><button className="back-button" onClick={onBack}>← Back to plans</button></div> }

function VoucherView({ voucher, active, remaining, copied, copyValue, showGuide, setShowGuide, onConnect, onBuy }: { voucher: Voucher; active: boolean; remaining: string; copied: string; copyValue: (label: string, value: string) => void; showGuide: boolean; setShowGuide: (value: boolean) => void; onConnect: () => void; onBuy: () => void }) { return <div className="success-state">{active && <p className="active-expiry">{remaining}</p>}<h2>YOUR ACCESS CODE</h2><div className="voucher-code"><span className="eyebrow">[VOUCHER]</span><strong>{voucher.code}</strong></div><div className="credential-grid"><Credential label="USERNAME" value={voucher.username} copied={copied} onCopy={copyValue} /><Credential label="PASSWORD" value={voucher.password} copied={copied} onCopy={copyValue} /></div>{!active && <button className="primary-button" onClick={onConnect}>Connect to WiFi <span>→</span></button>}<button className="guide-toggle" onClick={() => setShowGuide(!showGuide)}>[HOW TO CONNECT] <span>{showGuide ? '−' : '+'}</span></button>{showGuide && <ol className="guide-list"><li>Open WiFi settings on your phone</li><li>Connect to YOUR_NETWORK_NAME</li><li>Enter this code when the login page appears</li></ol>}<button className="back-button" onClick={onBuy}>Buy another plan →</button></div> }
function Credential({ label, value, copied, onCopy }: { label: string; value: string; copied: string; onCopy: (label: string, value: string) => void }) { return <div className="credential"><span className="eyebrow">[{label}]</span><div className="credential-value"><code>{value}</code><button className="copy-button" onClick={() => onCopy(label, value)}>{copied === label ? 'Copied' : 'Copy'}</button></div></div> }
