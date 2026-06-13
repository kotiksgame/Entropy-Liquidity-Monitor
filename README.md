# Entropy-Liquidity-Monitor
Institutional-grade cryptocurrency order flow analytics terminal using Shannon entropy for liquidity imbalance detection. Real-time Binance WebSocket integration.
**ELM** is a professional terminal for analyzing the microstructure of the cryptocurrency market in real time. The system is based on a mathematical analysis of information chaos (entropy) and liquidity imbalance.

## 🧠 Project philosophy
Market price is a consequence. Liquidity in the order book is the reason. ELM allows you to look under the hood of an exchange using:
- **Shannon Entropy:** Estimation of the uniformity of the distribution of limit orders.
- **Order Flow Imbalance (OFI):** Vector analysis of Bid/Ask pressure.
- **Health Metric:** Integral indicator of the sustainability of the current trend.

- ## 🚀 Tech stack
- **Language:** Python 3.9+
- **Interface:** Streamlit (Dark Mode)
- **Data:** Binance WebSockets (Spot & Futures)
- **Libraries:** Pandas, NumPy, CCXT, Plotly
-## 💻 Installation and launch

bash
# Cloning
git clone https://github.com/kotiksgame/Entropy-Liquidity-Monitor.git
cd Entropy-Liquidity-Monitor

#Environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Launch (RU)
streamlit run app.py --server.port 8501

# Run (EN)
streamlit run app_en.py --server.port 8502 
#RU
# 📊 Entropy Liquidity Monitor (ELM)

**ELM** — это профессиональный терминал для анализа микроструктуры криптовалютного рынка в реальном времени. В основе системы лежит математический анализ информационного хаоса (энтропии) и дисбаланса ликвидности.

## 🧠 Философия проекта
Рыночная цена — это следствие. Ликвидность в стакане — это причина. ELM позволяет "заглянуть под капот" биржи, используя:
- **Shannon Entropy:** Оценка равномерности распределения лимитных ордеров.
- **Order Flow Imbalance (OFI):** Векторный анализ давления Bid/Ask.
- **Health Metric:** Интегральный показатель устойчивости текущего тренда.

## 🚀 Технический стек
- **Язык:** Python 3.9+
- **Интерфейс:** Streamlit (Dark Mode)
- **Данные:** Binance WebSockets (Spot & Futures)
- **Библиотеки:** Pandas, NumPy, CCXT, Plotly

## 💻 Установка и запуск

bash
# Клонирование
git clone https://github.com/kotiksgame/Entropy-Liquidity-Monitor.git
cd Entropy-Liquidity-Monitor

# Окружение
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Запуск (RU)
streamlit run app.py --server.port 8501

# Run (EN)
streamlit run app_en.py --server.port 8502
