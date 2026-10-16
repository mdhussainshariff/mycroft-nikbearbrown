import { useState } from 'react'
import './App.css'

const API_BASE = 'http://127.0.0.1:8000'

function classifyError(err, status) {
  if (!status) {
    return 'Could not reach the backend — make sure the API server is running on port 8000.'
  }
  if (status === 404) {
    return 'Patent not found. Check the publication number format — it should look like US-11791319-B2 (with dashes and a kind code).'
  }
  if (status === 500) {
    return 'The server hit an error processing this patent. If classify is on, check that the API key is loaded correctly.'
  }
  return `Unexpected error (status ${status}).`
}

function App() {
  const [publicationNumber, setPublicationNumber] = useState('')
  const [classify, setClassify] = useState(false)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!publicationNumber.trim()) return

    setLoading(true)
    setError(null)
    setResult(null)

    let status = null

    try {
      const url = `${API_BASE}/patent/${encodeURIComponent(publicationNumber.trim())}?classify=${classify}`
      const response = await fetch(url)
      status = response.status

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}))
        throw new Error(errorBody.detail || '')
      }

      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError(classifyError(err, status))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <h1>Patent Reader</h1>
      <p className="subtitle">
        Real claims + citation lineage, read from BigQuery and Claude.
      </p>

      <form onSubmit={handleSubmit} className="search-form">
        <input
          type="text"
          value={publicationNumber}
          onChange={(e) => setPublicationNumber(e.target.value)}
          placeholder="e.g. US-11791319-B2"
          className="patent-input"
          disabled={loading}
        />
        <label className="classify-toggle">
          <input
            type="checkbox"
            checked={classify}
            onChange={(e) => setClassify(e.target.checked)}
            disabled={loading}
          />
          Classify scope (uses Claude API — small real cost)
        </label>
        <button type="submit" disabled={loading || !publicationNumber.trim()}>
          {loading ? (
            <span className="loading-row">
              <span className="spinner" />
              {classify ? 'Reading + classifying…' : 'Reading…'}
            </span>
          ) : 'Read Patent'}
        </button>
      </form>

      {loading && (
        <p className="loading-hint">
          {classify
            ? 'Fetching from BigQuery and running scope classification via Claude — this takes a few seconds.'
            : 'Fetching from BigQuery…'}
        </p>
      )}

      {error && (
        <div className="error">
          <strong>Error</strong>
          <p>{error}</p>
        </div>
      )}

      {result && (
        <div className="result">
          <h2>{result.publication_number}</h2>

          {result.claims && (
            <section>
              <h3>Claims</h3>
              <p>
                {result.claims.total_claims} total —{' '}
                {result.claims.independent_count} independent,{' '}
                {result.claims.dependent_count} dependent
              </p>
              {result.claims.flagged_for_manual_review?.length > 0 && (
                <p className="flag">
                  Flagged for manual review: {result.claims.flagged_for_manual_review.join(', ')}
                </p>
              )}
              {result.claims.scope_readings?.length > 0 && (
                <div className="scope-readings">
                  {result.claims.scope_readings.map((reading) => (
                    <div key={reading.claim} className="scope-reading">
                      <strong>Claim {reading.claim}</strong>: {reading.breadth} / {reading.posture}
                      <p className="caveat">{reading.confidence_caveat}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {result.lineage && (
            <section>
              <h3>Lineage</h3>
              <p>
                {result.lineage.total_citations} total citations —{' '}
                {result.lineage.patent_citations} patent,{' '}
                {result.lineage.non_patent_literature_citations} NPL
              </p>
              {result.lineage.cited_publication_numbers?.length > 0 && (
                <details>
                  <summary>
                    Cited publications ({result.lineage.cited_publication_numbers.length})
                  </summary>
                  <ul>
                    {result.lineage.cited_publication_numbers.map((num) => (
                      <li key={num}>{num}</li>
                    ))}
                  </ul>
                </details>
              )}
            </section>
          )}
        </div>
      )}
    </div>
  )
}

export default App
