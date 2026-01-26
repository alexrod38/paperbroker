from .QuoteAdapter import QuoteAdapter
# Try to import GoogleFinanceQuoteAdapter, but make it optional.
try:
    from .GoogleFinanceQuoteAdapter import GoogleFinanceQuoteAdapter
except Exception:
    GoogleFinanceQuoteAdapter = None
