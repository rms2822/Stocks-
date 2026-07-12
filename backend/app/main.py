from fastapi.staticfiles import StaticFiles
from datetime import date, timedelta
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .database import SessionLocal, engine
from . import models, schemas
from .crud import (
    create_stock, get_stock, get_all_stocks, delete_stock,
    save_dse_data, get_price_history, get_price_history_range,
    get_fundamentals, save_fundamentals,
)
from .dse_scraper import fetch_dse_data
from .fundamental_scraper import fetch_pe_data
from .analysis.technical import compute_technical_analysis
from .analysis.fundamental import compute_fundamental_analysis
from .analysis.fundamental_inputs import build_fundamental_kwargs

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="DSE Analyzer API",
    description="Fundamental + technical analysis for Dhaka Stock Exchange",
    version="3.0.0",
)

app.mount("/static", StaticFiles(directory="."), name="static")
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# â”€â”€ DB dependency â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# â”€â”€ Health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/", tags=["health"])
def home():
    return {"message": "DSE Analyzer API", "version": "3.0.0"}


# â”€â”€ Data loading â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.post("/load-dse", response_model=schemas.LoadDSEResponse, tags=["data"])
def load_dse(db: Session = Depends(get_db)):
    """
    Scrape latest prices from DSE and upsert stocks + price_history.
    Call this daily (or set up a scheduler).
    """
    try:
        df = fetch_dse_data()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DSE price scrape failed: {e}")

    summary = save_dse_data(df, db)
    return {"message": "DSE data loaded", "total_scraped": len(df), **summary}


@app.post("/load-fundamentals", response_model=schemas.LoadFundamentalsResponse, tags=["data"])
def load_fundamentals(db: Session = Depends(get_db)):
    """
    Fetch EPS, P/E, NAV for all DSE stocks from amarstock's market-pe API.
    Single request covers all ~400 stocks instantly.
    Call this daily â€” values update when companies publish quarterly results.
    """
    try:
        df = fetch_pe_data()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fundamentals scrape failed: {e}")

    summary = save_fundamentals(df, db)
    return {
        "message": "Fundamentals loaded",
        "total_scraped": len(df),
        **summary,
    }


# â”€â”€ Stocks â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.post("/stocks", status_code=201, response_model=schemas.StockOut, tags=["stocks"])
def add_stock(
    ticker:  str = Query(...),
    company: str = Query(None),
    sector:  str = Query(None),
    db: Session = Depends(get_db),
):
    return create_stock(db=db, ticker=ticker, company=company, sector=sector)


@app.get("/stocks", tags=["stocks"])
def list_stocks(db: Session = Depends(get_db)):
    stocks = get_all_stocks(db)
    return {"total": len(stocks), "stocks": stocks}


@app.get("/stocks/{ticker}", response_model=schemas.StockOut, tags=["stocks"])
def get_stock_by_ticker(ticker: str, db: Session = Depends(get_db)):
    stock = get_stock(db, ticker)
    if not stock:
        raise HTTPException(status_code=404, detail=f"'{ticker.upper()}' not found")
    return stock


@app.delete("/stocks/{ticker}", tags=["stocks"])
def remove_stock(ticker: str, db: Session = Depends(get_db)):
    if not delete_stock(db, ticker):
        raise HTTPException(status_code=404, detail=f"'{ticker.upper()}' not found")
    return {"message": f"{ticker.upper()} deleted"}


# â”€â”€ Price history â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get("/stocks/{ticker}/history", response_model=schemas.HistoryResponse, tags=["history"])
def price_history(
    ticker: str,
    limit:  int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    stock = get_stock(db, ticker)
    if not stock:
        raise HTTPException(status_code=404, detail=f"'{ticker.upper()}' not found")
    rows = get_price_history(db, ticker, limit=limit)
    return {"ticker": ticker.upper(), "company": stock.company, "count": len(rows), "history": rows}


@app.get("/stocks/{ticker}/history/range", response_model=schemas.HistoryResponse, tags=["history"])
def price_history_range(
    ticker: str,
    start:  date = Query(...),
    end:    date = Query(...),
    db: Session = Depends(get_db),
):
    if start > end:
        raise HTTPException(status_code=400, detail="start must be before end")
    stock = get_stock(db, ticker)
    if not stock:
        raise HTTPException(status_code=404, detail=f"'{ticker.upper()}' not found")
    rows = get_price_history_range(db, ticker, start, end)
    return {"ticker": ticker.upper(), "company": stock.company, "count": len(rows), "history": rows}


# â”€â”€ Analysis â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.get(
    "/stocks/{ticker}/analysis/technical",
    response_model=schemas.TechnicalAnalysisOut,
    tags=["analysis"],
)
def technical_analysis(
    ticker: str,
    days:   int = Query(200, ge=14, le=1000),
    db: Session = Depends(get_db),
):
    """RSI, MACD, SMA, EMA, Bollinger Bands with BUY/HOLD/SELL signal."""
    stock = get_stock(db, ticker)
    if not stock:
        raise HTTPException(status_code=404, detail=f"'{ticker.upper()}' not found")
    rows   = get_price_history(db, ticker, limit=days)
    result = compute_technical_analysis(ticker, rows)
    return {
        "ticker":         result.ticker,
        "current_price":  result.current_price,
        "recommendation": result.recommendation,
        "score":          result.score,
        "data_days":      result.data_days,
        "warning":        result.warning,
        "indicators":     vars(result.indicators),
        "signals":        [vars(s) for s in result.signals],
    }


@app.get(
    "/stocks/{ticker}/analysis/fundamental",
    response_model=schemas.FundamentalAnalysisOut,
    tags=["analysis"],
)
def fundamental_analysis(ticker: str, db: Session = Depends(get_db)):
    """P/E, P/B, EPS, NAV, dividend yield scoring with BUY/HOLD/SELL signal."""
    stock = get_stock(db, ticker)
    if not stock:
        raise HTTPException(status_code=404, detail=f"'{ticker.upper()}' not found")

    fund = get_fundamentals(db, ticker)

    eps_hist = {}
    if fund:
        for yr, attr in [(2021,"eps_2021"),(2022,"eps_2022"),(2023,"eps_2023"),(2024,"eps_2024"),(2025,"eps_2025")]:
            v = getattr(fund, attr, None)
            if v is not None: eps_hist[yr] = v

    result = compute_fundamental_analysis(**build_fundamental_kwargs(stock, fund))

    return {
        "ticker":         result.ticker,
        "current_price":  result.current_price,
        "recommendation": result.recommendation,
        "score":          result.score,
        "eps":            result.eps,
        "pe":             result.pe,
        "nav":            result.nav,
        "pb":             result.pb,
        "dividend_yield": result.dividend_yield,
        "roe":            result.roe,
        "sector":         result.sector,
        "sector_pe":      result.sector_pe,
        "warning":        result.warning,
        "signals":        [vars(s) for s in result.signals],
    }


@app.get(
    "/stocks/{ticker}/analysis",
    response_model=schemas.CombinedAnalysisOut,
    tags=["analysis"],
)
def combined_analysis(
    ticker:       str,
    days:         int   = Query(200, ge=14, le=1000),
    tech_weight:  float = Query(0.45, ge=0.0, le=1.0, description="Technical weight (0-1)"),
    fund_weight:  float = Query(0.55, ge=0.0, le=1.0, description="Fundamental weight (0-1)"),
    db: Session = Depends(get_db),
):
    """
    Full combined analysis â€” technical + fundamental in one response.

    Weights default to 55% fundamental / 45% technical.
    Adjust via query params: ?tech_weight=0.5&fund_weight=0.5
    """
    stock = get_stock(db, ticker)
    if not stock:
        raise HTTPException(status_code=404, detail=f"'{ticker.upper()}' not found")

    # Normalise weights so they always sum to 1
    total = tech_weight + fund_weight
    tw    = tech_weight / total
    fw    = fund_weight / total

    # Technical
    history_rows = get_price_history(db, ticker, limit=days)
    tech = compute_technical_analysis(ticker, history_rows)

    # Fundamental
    fund_row = get_fundamentals(db, ticker)
    eps_hist2 = {}
    if fund_row:
        for yr, attr in [(2021,"eps_2021"),(2022,"eps_2022"),(2023,"eps_2023"),(2024,"eps_2024"),(2025,"eps_2025")]:
            v = getattr(fund_row, attr, None)
            if v is not None: eps_hist2[yr] = v
    fund = compute_fundamental_analysis(**build_fundamental_kwargs(stock, fund_row))

    # Combined score
    combined_score = round(tech.score * tw + fund.score * fw, 1)

    if combined_score >= 62:
        combined_rec = "BUY"
    elif combined_score >= 42:
        combined_rec = "HOLD"
    else:
        combined_rec = "SELL"

    # Merge warnings
    warnings = [w for w in [tech.warning, fund.warning] if w]
    warning  = " | ".join(warnings) if warnings else None

    return {
        "ticker":         ticker.upper(),
        "current_price":  stock.ltp or stock.close or 0,
        "sector":         stock.sector,
        "company":        stock.company,
        "recommendation": combined_rec,
        "combined_score": combined_score,
        "tech_score":     tech.score,
        "fund_score":     fund.score,
        "data_days":      tech.data_days,
        "warning":        warning,
        "technical": {
            "ticker":         tech.ticker,
            "current_price":  tech.current_price,
            "recommendation": tech.recommendation,
            "score":          tech.score,
            "data_days":      tech.data_days,
            "warning":        tech.warning,
            "indicators":     vars(tech.indicators),
            "signals":        [vars(s) for s in tech.signals],
        },
        "fundamental": {
            "ticker":         fund.ticker,
            "current_price":  fund.current_price,
            "recommendation": fund.recommendation,
            "score":          fund.score,
            "eps":            fund.eps,
            "pe":             fund.pe,
            "nav":            fund.nav,
            "pb":             fund.pb,
            "dividend_yield": fund.dividend_yield,
            "roe":            fund.roe,
            "sector":         fund.sector,
            "sector_pe":      fund.sector_pe,
            "warning":        fund.warning,
            "signals":        [vars(s) for s in fund.signals],
        },
    }


# â”€â”€ Screener â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

from .analysis.screener import run_screener

@app.get("/screener", response_model=schemas.ScreenerResponse, tags=["analysis"])
def screener(
    sector:          Optional[str]   = Query(None, description="e.g. 'Pharmaceuticals and Chemicals' or 'Bank'"),
    min_eps:         Optional[float] = Query(None, description="Minimum EPS"),
    max_eps:         Optional[float] = Query(None, description="Maximum EPS"),
    min_pe:          Optional[float] = Query(None, description="Minimum P/E"),
    max_pe:          Optional[float] = Query(None, description="Maximum P/E (e.g. 15 for value stocks)"),
    profitable_only: bool            = Query(False, description="Only include stocks with positive EPS"),
    min_tech_score:  Optional[float] = Query(None, description="Minimum technical score 0-100"),
    min_score:       Optional[float] = Query(None, description="Minimum combined score 0-100"),
    recommendation:  Optional[str]   = Query(None, description="BUY | HOLD | SELL"),
    limit:           int             = Query(30, ge=1, le=200),
    sort_by:         str             = Query("combined_score", description="combined_score | tech_score | fund_score | pe | eps"),
    sort_dir:        str             = Query("desc", description="asc | desc"),
    tech_weight:     float           = Query(0.45, ge=0.0, le=1.0),
    fund_weight:     float           = Query(0.55, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    """
    Screen all DSE stocks by fundamental and technical criteria.

    Examples:
      /screener?profitable_only=true&max_pe=15&recommendation=BUY
      /screener?sector=Bank&min_tech_score=60&limit=10
      /screener?min_score=65&sort_by=pe&sort_dir=asc
    """
    from typing import Optional as Opt
    results = run_screener(
        db              = db,
        sector          = sector,
        min_eps         = min_eps,
        max_eps         = max_eps,
        min_pe          = min_pe,
        max_pe          = max_pe,
        profitable_only = profitable_only,
        min_tech_score  = min_tech_score,
        min_score       = min_score,
        recommendation  = recommendation,
        limit           = limit,
        sort_by         = sort_by,
        sort_dir        = sort_dir,
        tech_weight     = tech_weight,
        fund_weight     = fund_weight,
    )

    active_filters = {k: v for k, v in {
        "sector": sector, "min_eps": min_eps, "max_eps": max_eps,
        "min_pe": min_pe, "max_pe": max_pe, "profitable_only": profitable_only,
        "min_tech_score": min_tech_score, "min_score": min_score,
        "recommendation": recommendation,
    }.items() if v is not None and v is not False}

    return {
        "total":   len(results),
        "filters": active_filters,
        "results": results,
    }


# â”€â”€ Historical data loader â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

from .history_loader import bulk_load_history

@app.post("/load-history", tags=["data"])
def load_history(
    days:   int          = Query(365, ge=30, le=1500, description="Days of history to backfill"),
    ticker: Optional[str] = Query(None, description="Single ticker â€” omit for all stocks"),
    db: Session = Depends(get_db),
):
    """
    Backfill historical OHLCV price data using bdshare.

    - Single stock:  POST /load-history?days=365&ticker=ACI  (~2 seconds)
    - All stocks:    POST /load-history?days=365             (~15-30 minutes)

    Run single-stock first to verify, then run all stocks overnight.
    Data is upserted â€” safe to re-run, won't duplicate rows.
    """
    if ticker:
        tickers = [ticker.upper()]
    else:
        tickers = [s.ticker for s in get_all_stocks(db)]

    if not tickers:
        raise HTTPException(status_code=400, detail="No stocks in DB. Call POST /load-dse first.")

    try:
        summary = bulk_load_history(tickers=tickers, days=days, db=db)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"History load failed: {e}")

    return {
        "message": "History loaded",
        "date_range": f"{(date.today() - __import__('datetime').timedelta(days=days)).isoformat()} â†’ {date.today().isoformat()}",
        **summary,
    }
from fastapi.responses import FileResponse

@app.get('/dashboard')
def dashboard():
    return FileResponse('dashboard.html', media_type='text/html; charset=utf-8')




from app.models import Portfolio as PortfolioModel, Stock as StockModel

@app.get('/portfolio')
def get_portfolio(db: Session = Depends(get_db)):
    holdings = db.query(PortfolioModel).all()
    result = []
    for h in holdings:
        stock = db.query(StockModel).filter(StockModel.ticker == h.ticker).first()
        if not stock:
            continue
        current_price = stock.ltp or 0
        invested = h.buy_price * h.quantity
        current_value = current_price * h.quantity
        pl = current_value - invested
        pl_pct = (pl / invested * 100) if invested > 0 else 0
        rec, score = 'HOLD', 0
        try:
            history_rows = get_price_history(db, h.ticker, limit=200)
            tech = compute_technical_analysis(h.ticker, history_rows)
            fund_row = get_fundamentals(db, h.ticker)
            eps_hist = {}
            if fund_row:
                for yr, attr in [(2021,"eps_2021"),(2022,"eps_2022"),(2023,"eps_2023"),(2024,"eps_2024"),(2025,"eps_2025")]:
                    v = getattr(fund_row, attr, None)
                    if v is not None: eps_hist[yr] = v
            fund = compute_fundamental_analysis(**build_fundamental_kwargs(stock, fund_row))
            combined = round(tech.score * 0.45 + fund.score * 0.55, 1)
            if combined >= 62: rec = "BUY"
            elif combined >= 42: rec = "HOLD"
            else: rec = "SELL"
            score = combined
        except Exception:
            pass
        result.append({'ticker': h.ticker, 'buy_price': h.buy_price, 'quantity': h.quantity,
            'current_price': current_price, 'invested': round(invested, 2),
            'current_value': round(current_value, 2), 'pl': round(pl, 2),
            'pl_pct': round(pl_pct, 2), 'recommendation': rec, 'score': score,
            'sector': stock.sector})
    return result

@app.post('/portfolio')
def add_holding(ticker: str, buy_price: float, quantity: float, db: Session = Depends(get_db)):
    ticker = ticker.upper()
    stock = db.query(StockModel).filter(StockModel.ticker == ticker).first()
    if not stock:
        raise HTTPException(status_code=404, detail=f'Ticker {ticker} not found')
    existing = db.query(PortfolioModel).filter(PortfolioModel.ticker == ticker).first()
    if existing:
        existing.buy_price = buy_price
        existing.quantity = quantity
    else:
        db.add(PortfolioModel(ticker=ticker, buy_price=buy_price, quantity=quantity))
    db.commit()
    return {'message': f'{ticker} added to portfolio'}

@app.delete('/portfolio/{ticker}')
def remove_holding(ticker: str, db: Session = Depends(get_db)):
    h = db.query(PortfolioModel).filter(PortfolioModel.ticker == ticker.upper()).first()
    if not h:
        raise HTTPException(status_code=404, detail='Not found')
    db.delete(h)
    db.commit()
    return {'message': f'{ticker} removed'}

@app.get('/portfolio/analysis')
def portfolio_analysis(db: Session = Depends(get_db)):
    holdings = get_portfolio(db)
    if not holdings:
        return {'message': 'Portfolio is empty'}
    total_invested = sum(h['invested'] for h in holdings)
    total_value = sum(h['current_value'] for h in holdings)
    total_pl = total_value - total_invested
    total_pl_pct = (total_pl / total_invested * 100) if total_invested > 0 else 0
    avg_score = sum(h['score'] for h in holdings) / len(holdings)
    sell = [h for h in holdings if h['recommendation'] == 'SELL']
    hold = [h for h in holdings if h['recommendation'] == 'HOLD']
    buy_more = [h for h in holdings if h['recommendation'] == 'BUY']
    try:
        from .analysis.screener import run_screener
        screener_results = run_screener(db=db, profitable_only=True, max_pe=15.0, limit=5)
        top_buys = [vars(r) for r in screener_results] if screener_results else []
    except Exception:
        top_buys = []
    return {'summary': {'total_invested': round(total_invested, 2), 'total_value': round(total_value, 2),
        'total_pl': round(total_pl, 2), 'total_pl_pct': round(total_pl_pct, 2),
        'avg_score': round(avg_score, 1), 'holdings_count': len(holdings)},
        'sell_suggestions': sell, 'hold': hold, 'buy_more': buy_more, 'top_buy_opportunities': top_buys}


