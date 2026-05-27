'use client'
import React from 'react'

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode, fallback?: React.ReactNode },
  { hasError: boolean, error: Error | null }
> {
  constructor(props: any) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="p-6 bg-red-950/40 text-red-400 rounded-xl border border-red-900/50 backdrop-blur-sm max-w-lg w-full shadow-2xl">
          <h2 className="font-semibold text-lg mb-2">Critical Rendering Failure</h2>
          <p className="text-sm opacity-80 font-mono">{this.state.error?.message}</p>
          <button 
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-4 px-4 py-2 bg-red-900/50 hover:bg-red-900/80 rounded transition-colors text-xs"
          >
            Attempt Recovery
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
