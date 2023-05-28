Tradingview alerts.

Open Long (Buy)

{
  "ticker": "{{ticker}}",
  "strategy": {
    "order": {
      "action": "Buy"
    }
  }
}


Close Long (Sell)

{
  "ticker": "{{ticker}}",
  "strategy": {
    "order": {
      "action": "Exit"
    }
  }
}


Open Short (Sell)

{
  "ticker": "{{ticker}}",
  "strategy": {
    "order": {
      "action": "Sell"
    }
  }
}


Close Short (Buy)

{
  "ticker": "{{ticker}}",
  "strategy": {
    "order": {
      "action": "Exit"
    }
  }
}