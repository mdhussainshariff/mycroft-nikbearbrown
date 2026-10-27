import { useState } from 'react'
import './App.css'

const API_BASE = 'http://127.0.0.1:8000'

function App() {
  const [publicationNumber, setPublicationNumber] = useState('')
  const [classify, setClassify] = useState(true)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!publicationNumber.trim()) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const url = `${API_BASE}/patent/${encodeURIComponent(publicationNumber.trim())}?classify=${classify}`
      const response = await fetch(url)

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorBody.detail || `Request failed with status ${response.status}`)
      }

      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <div className="masthead">
        <h1>Patent Reader</h1>
        <p>Pulls claims structure and citation lineage straight from BigQuery, with optional Claude-based scope classification.</p>
      </div>

      <form onSubmit={handleSubmit} className="query-row">
        <input
          type="text"
          value={publicationNumber}
          onChange={(e) => setPublicationNumber(e.target.value)}
          placeholder="e.g. US-11791319-B2"
          className="patent-input"
        />
        <button type="submit" disabled={loading}>
          {loading ? 'Reading…' : 'Read patent'}
        </button>
      </form>

      <label className="classify-row">
        <input
          type="checkbox"
          checked={classify}
          onChange={(e) => setClassify(e.target.checked)}
        />
        Classify scope
        <span className="cost">uses Claude — small real cost, skipped if off</span>
      </label>

      {error && <div className="error-banner">Error: {error}</div>}

      {!result && !error && !loading && (
        <div className="empty-hint">Enter a publication number above to read its claims and lineage.</div>
      )}

      {result && (
        <div className="record">
          <div className="record-header">
            <span className="num">{result.publication_number}</span>
            <span className="kind">classify: {String(classify)}</span>
          </div>

          {result.claims && (
            <div className="section claims">
              <div className="section-head">
                <span className="dot"></span>
                <h2>Claims</h2>
              </div>
              <div className="stat-line">
                <span className="figure">{result.claims.total_claims}</span> total claims —{' '}
                <span className="figure">{result.claims.independent_count}</span> independent,{' '}
                <span className="figure">{result.claims.dependent_count}</span> dependent
              </div>
              <p className="gloss">
                Independent claims define the invention on their own. Dependent claims narrow one of those
                down with an added detail — more of them means more fallback positions if the broad claim
                gets challenged.
              </p>

              {result.claims.flagged_for_manual_review?.length > 0 && (
                <p className="flag">
                  Flagged for manual review: {result.claims.flagged_for_manual_review.join(', ')}
                </p>
              )}

              {result.claims.scope_readings?.map((reading) => (
                <div key={reading.claim} className="scope-reading">
                  <span className="claim-tag">Claim {reading.claim}</span>
                  <span className="reading-line">{reading.breadth} / {reading.posture}</span>
                  <p className="caveat">{reading.confidence_caveat}</p>
                </div>
              ))}
            </div>
          )}

          {result.lineage && (
            <div className="section lineage">
              <div className="section-head">
                <span className="dot"></span>
                <h2>Lineage</h2>
              </div>
              <div className="stat-line">
                <span className="figure">{result.lineage.total_citations}</span> total citations —{' '}
                <span className="figure">{result.lineage.patent_citations}</span> patent,{' '}
                <span className="figure">{result.lineage.non_patent_literature_citations}</span> non-patent literature
              </div>
              <p className="gloss">
                Backward citations — the prior work this patent points to as related art. Patent citations
                are earlier patents; non-patent literature is papers, standards, or other published sources
                it references or distinguishes itself from.
              </p>

              {result.lineage.cited_publication_numbers?.length > 0 && (
                <details className="cited">
                  <summary>Cited publications ({result.lineage.cited_publication_numbers.length})</summary>
                  <div className="cite-list">
                    {result.lineage.cited_publication_numbers.map((num) => (
                      <div key={num} className="cite-item">{num}</div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default App
