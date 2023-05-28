# vaCaCalculator

CA, VA 분산투자를 자동적으로 계산해주는 파이썬 프로그램입니다. 증권의 경우 한국투자 Open API를 활용하여 국내주 및 미국주의 주가 뿐 아니라 종목별 잔고도 조회 가능하고, 증권 외에 암호화폐, KRX 금현물, 현금에 대한 분산투자도 계산 가능하도록 구성돼 있습니다. 한가지 특기할 만한 점으로 분산투자의 기준화폐가 원화가 아닌 달러화로 설정돼 있는데 이는 외국인 투자자와 보다 동조되는 방향으로 투자가 이뤄지도록 하기 위함입니다.

## 분산투자 동작방식 설명
### CA (Cost Averaging)
DCA(Dollar Cost Averaging)라고도 불리는 방식으로 매 투자주기마다 일정한 금액을 투자하는 가장 간단한 분산투자 방식이라고 할 수 있습니다. 주식의 예를 들면, 투자 주기가 한 달이라고 할 때 매달 100만원 어치의 주식을 매수합니다. 이 방식으로 투자할 때는 매도하는 경우가 전혀 없다는 점이 특징이라고 할 수 있습니다.

본 프로그램은 매 주기의 저축액이 같을 수 없음을 고려하여 저축액이 주어졌을 때 각 종목별로 설정된 투자비중에 따라 종목별 가격을 조회하여 매수필요량을 산출해 주는 방식으로 구성돼 있습니다.

### VA (Value Averaging)

CA보다 복잡한 분산투자 방식으로 매 투자주기마다 자산의 평가금액을 일정하게 늘려가는 방식입니다. 주식의 예를 들면, 투자 주기가 한 달이라고 했을 때, 자산 평가금액을 매달 100만원씩 증가하도록 매수도를 수행합니다. 첫째 달에는 100만원 어치의 주식을 구매하는 것으로 시작합니다. 둘째 달이 되었을 때, 주가가 상승하여 평가금액이 150만원이 되었다면 50만원만 매수하고, 주가가 하락하여 평가금액이 50만원이 되었다면 150만원을 매수하여 둘째 달의 자산 평가금액을 200만원이 되도록 설정합니다. 이와 같이 계속 매 달마다 평가금액이 100만원 * 개월수가 되도록 매수도를 수행합니다. CA와 다르게 자산의 급격한 가치상승이 있을 경우 매도하는 경우가 발생할 수 있습니다.

CA의 경우와 마찬가지로 본 프로그램은 매 주기의 저축액이 같을 수 없음을 고려하여 매 투자주기의 평가금액 증가분을 각 종목별로 설정된 투자비중과 각 투자주기의 저축액으로부터 산출합니다.

## 환경 설정
### 파이썬 환경 설정
Python3 pip와 virtual environment를 이용하여 아래와 같이 설정 가능합니다(데비안-우분투 기준으로 설명).

```
$ cd $PROJECTPATH
$ sudo apt install python3-pip python3-venv
$ python3 -m venv venv
$ source venv/bin/activate
$ python3 -m pip install -U pip
$ python3 -m pip install -R pip-requirements
```

### Secret 설정
소스코드 파일에 token, API key 등 비밀정보 노출 방지를 위해 모든 비밀정보는 별도 파일인 secrets.json 파일에 별도 보관하도록 설정돼 있습니다. 해당 파일은 본 GitHub 저장소에 포함돼 있지 않으므로 파일을 별도로 생성해 주어야 하며 파일의 이름은 반드시 "secrets.json" 이어야 합니다. 현재 기준으로 비밀정보를 필요로 하는 서비스는 아래와 같습니다. 회원가입 및 서비스 신청 후 발급받은 비밀정보를 secrets.json에 후술되는 형식으로 저장합니다.

#### 환율 조회
한국수출입은행 Open API를 이용합니다. https://www.koreaexim.go.kr/ir/HPHKIR019M01 의 현재환율 API를 참조하여 현재환율 조회를 위한 인증키를 발급받으십시오.

#### 한국투자 Open API - 선택
국내 및 해외주식 가격 및 보유잔고 조회를 위해 필요합니다. 만약 한국투자증권을 사용하지 않으시거나 국내/해외 주식을 포트폴리오에 포함하지 않는 경우 필요치 않습니다. 신청을 위해서는 KIS Developers(https://apiportal.koreainvestment.com/intro#)의 API신청으로 이동하여 한국투자 회원가입 후 APP key와 secret을 발급받으십시오.

#### secrets.json 파일 형식
발급된 비밀정보를 아래의 형식으로 입력합니다.

```
{
	"ExchangerateSecrets": {
		"AUTH_KEY": "한국수출입은행_현재환율API_인증키"
	},
	"KisSecrets": {
		"APP_KEY": "한국투자증권_OpenAPI_APP_KEY",
		"APP_SECRET": "한국투자증권_OpenAPI_APP_SECRET"
	}
}
```

한국투자 API를 사용하지 않는 경우 아래와 같이 "KisSecrets" 항목을 제외하고 "ExchangerateSecrets" 항목만으로 json을 구성합니다.

```
{
	"ExchangerateSecrets": {
		"AUTH_KEY": "한국수출입은행_현재환율API_인증키"
	}
}
```

### 포트폴리오 및 분산투자방식 설정
본 프로그램은 각 종목별로 산출된 투자필요수량 및 각종 정보들을 JSON 형식의 투자보고서 파일로 출력하는데, 최초 프로그램 활용을 위한 입력정보도 유사한 형식의 투자보고서를 작성함으로써 이루어집니다. 아래의 예시 JSON 파일을 참조하여 최초 포트폴리오 설정을 위한 JSON 파일을 작성하십시오. JSON 파일 내의 각 항목에 대한 보다 자세한 설명은 후술합니다.

```
{
	"strategy": "VA",
	"stockgroups":
	{
		"KIS":
		{
			"accountNo": "12345678-01",
			"stocks":
			{
				"069500":
				{
					"weight": 0.25,
					"market": "DOM",
					"holdings": 50,
					"price": 30000,
					"currency": "KRW",
					"descr": "KODEX200"
				},
				"VOO":
				{
					"weight": 0.25,
					"market": "AMS",
					"currency": "USD",
					"descr": "Vanguard S&P 500 ETF"
				}
			}
		},
		"CoinGecko":
		{
			"stocks":
			{
				"BTC":
				{
					"weight": 0.1,
					"holdings": 0.02,
					"cumSumCaInvestedInKRW": 1000000,
					"cumSumCaInvestedInUSD": 1000,
					"currency": "USD",
					"descr": "Bitcoin"
				},
				"ETH":
				{
					"weight": 0.1,
					"holdings": 0.2,
					"cumSumCaInvestedInKRW": 1000000,
					"cumSumCaInvestedInUSD": 1000,
					"currency": "USD",
					"descr": "Ethereum"
				}
			}
		},
		"KRX":
		{
			"stocks":
			{
				"GLD":
				{
					"weight": 0.1,
					"holdings": 10,
					"cumSumCaInvestedInKRW": 500000,
					"currency": "KRW",
					"descr": "GLD"
				}
			}
		},
		"OTHER":
		{
			"stocks":
			{
				"KRW":
				{
					"weight": 0.1,
					"holdings": 1000000,
					"price": 1,
					"cumSumCaInvestedInKRW": 1000000,
					"currency": "KRW",
					"descr": "KRW savings"
				},
				"USD":
				{
					"weight": 0.1,
					"holdings": 1000,
					"price": 1,
					"cumSumCaInvestedInUSD": 1000,
					"currency": "USD",
					"descr": "USD savings"
				}
			}
		}
	}
}
```

#### 최상위 항목
| 항목 | 설명 |
|------|------|
| `"strategy"` | 적용할 분산투자 전략 (CA/VA) |
| `"stockgroups"` | 증권/코인/금현물/현금성 상품그룹 dict |

#### stockgroups 요소
| 항목 | 설명 |
|------|------|
| `"KIS"` | 해외/국내 증권에 해당하는 상품들 |
| `"CoinGecko"` | 코인들.<br>CoinGecko API를 이용하여 가격정보를 수집하여 CoinGecko라고 명명하였음. |
| `"KRX"` | KRX 금현물.<br>주식시장이 아니라 KRX 금시장에 상장되어 거래되는 "금 현물 99.99_1kg" 상품. |
| `"OTHER"` | 예적금, 현금성 자산 등 가격이 고정돼 있는 상품들.<br>본 프로그램은 이자 등으로 인한 현금성 자산의 가격변동을 추적하지 않음. |

각 stockgroup은 중첩된 dict 형태로 구성돼 있으며 아래와 같은 요소들을 가집니다.

##### 공통요소
| 항목 | 설명 |
|------|------|
| `"stocks"` | 각 상품(stock)에 대한 정보를 포함하는 dict. |

##### KIS stockgroup 한정 요소
| 항목 | 설명 |
|------|------|
| `"accountNo"` | 한국투자증권 계좌번호 |

#### stocks 요소
| 항목 | 설명 |
|------|------|
| 상품 식별자 | 각 상품을 나타내는 식별자. stockgroup 별로 상이함. |

##### stockgroup 별 상품 식별자
| stockgroup | 설명 |
|------|------|
| `"KIS"` | 국내주: 종목코드 6자리 (e.g. KODEX200: 069500), 해외주: ticker 3글자 또는 4글자 (e.g. Vanguard S&P500 Index: VOO) |
| `"CoinGecko"` | 각 코인별 ticker 3자리.<br>현재 코드는 BTC(Bitcoin), ETH(Ethereum), BNB(Binance Coin)만 지원하나, stockwrapper.py GeckoStock class의 SYMB2ID_DICT와 ID2SYMB_DICT를 확장하면 CoinGecko가 지원하는 모든 코인으로 확장 가능 |
| `"KRX"` | `GLD`. KRX 금현물 하나의 상품을 위한 stockgroup으로서 상품 식별자는 `GLD` 하나만 사용 가능 |
| `"OTHER"` | 상품 식별자에 대한 제약 없음. OTHER stockgroup 내에서 중복되지만 않는 한 임의의 식별자 사용 가능 |

#### stock 요소
##### 공통요소
stockgroup의 종류와 무관하게 모든 stock에 적용 가능한 요소들

| 항목 | 설명 |
|------|------|
| `"weight"` | 투자비중.<br>stockgroup 별 비중이 아니라 전체 비중값을 입력. 즉, 모든 상품의 weight 합이 1.0이 돼야 함. |
| `"holdings"` (KIS: optional) | 상품별 기 보유수량.<br>KIS stockgroup의 경우 API에 의해 현 보유수량 수집이 가능하여 기재하지 않아도 됨(단, 이 경우 `cum_inv_deviation` 값이 달라질 수 있음. 이에 대해서는 후술.). |
| `"price"` (KIS, CoinGecko, KRX: optional) | 상품별 단가.<br>KIS, CoinGecko, KRX stockgroup의 경우 API에 의해 현 가격정보 수집이 가능하여 기재하지 않아도 됨(단, 이 경우 `"cum_inv_deviation"` 값이 달라질 수 있음. 이에 대해서는 후술.).
| `"currency"` | 상품단가의 표시통화.<br>상기 `"price"`항목이 어떤 통화로 돼 있는지를 표시. 해당 상품의 국내/해외시장 거래여부와는 무관하여 오직 `"price"` 항목과만 연관. |
| `"descr"` (optional) | 각 상품별 상세 설명.<br>코드상에서 사용되지 않으므로 생략해도 무방하나 json 파일을 분석하는 데 유용함. |
| `"cumSumCaInvested"` (optional) | 각 항목에 투자된 미화 기준 총액(cumulative sum of invested amount).<br>`"cumSumCaInvested"`, `"cumSumCaInvestedInKRW"`, `"cumSumCaInvestedInUSD"` 중 어느 하나도 제공되지 않은 경우 현재 상품의 미화 기준 평가금액(현재가*보유수량/환율)을 사용. |
| `"cumSumCaInvestedInKRW"` (`"cumSumCaInvested"` 미기재 시 한정) | 미화 대신 원화 기준 투자 총액을 사용할 경우 입력. 현재환율 적용하여 `"cumSumCaInvested"`로 자동 환산됨. `"cumSumCaInvested"` 기재 시 무시됨. |
| `"cumSumCaInvestedInUSD"` (`"cumSumCaInvested"` 미기재 시 한정) | 특정 상품에 대한 기존 투자 총액이 원화 뿐 아니라 미화로도 돼 있을 경우 입력하며, 두 항목이 합산되어 `"cumSumCaInvested"`로 설정됨. `"cumSumCaInvested"` 기재 시 무시됨. |

##### KIS stockgroup 한정 요소
| 항목 | 설명 |
|------|------|
| `"market"` | 한국투자 API에 사용되는 상품별 시장값 정보.<br>국내주의 경우 `"DOM"`, 해외(미국)주의 경우 `"NYS"`, `"NAS"`, `"AMS"` 중 하나임. 주의할 점으로 해외주의 경우 실제로는 뉴욕증권거래소(NYSE)에 상장된 주식인데 `"AMS"`를 입력해야 가격/보유수량 조회가 가능한 경우가 대부분이었음. |

## 활용
대략적으로 아래의 흐름으로 활용 가능합니다.

1. python3 interpreter로 main.py를 실행. 이때, 기 작성된 포트폴리오 JSON 파일을 입력 인수로 제공받으며, 분산투자결과가 기재된 출력 JSON 파일을 생성하여 프로그램이 종료됩니다.
2. 생성된 출력 JSON 파일을 참조하여 투자작업을 수동으로 수행합니다. 한국투자의 경우 매수도도 API로 가능하며, 특정 암호화폐 거래소 API를 이용 시 코인 매수도도 가능하나 현재는 자동 매수도 기능은 구현돼 있지 않습니다.
3. 상품별로 매수도한 수량을 출력 JSON 파일에 기재합니다. 아래 [실투자량 입력](#실투자량-입력) 항목 참조.
4. 다음 투자주기에 도달하면 최초의 경우와 마찬가지로 main.py를 실행하되, 이번에는 포트폴리오 JSON파일이 아니라 출력된 JSON 파일을 입력 파일로 삼아 실행합니다. 이를 기반으로 새로운 출력 JSON 파일이 생성됩니다.

### 프로그램 옵션 및 인수
본 프로그램은 명령창 인터페이스를 사용하며, `main.py`를 이용하여 활용됩니다. `main.py`에는 아래와 같은 옵션과 인수들이 있습니다.

| 항목 | 구분 | 설명 |
|------|------|------|
| `--debug-level` (optional) | kwarg | 프로그램의 로깅 레벨 설정.<br>미입력 시 기본값은 INFO이며 DEBUG, INFO, WARNING 중 하나 입력. |
| `--saving-in-krw` (optinoal) | kwarg | 해당 투자주기에 저축할 원화 기준 금액.<br>예를 들어, 100만원 저축 시 --saving-in-krw=1000000과 같이 입력. 미입력 시 기본값은 0임. |
| `--saving-in-usd` (optional) | kwarg | 해당 투자주기에 저축할 달러화 기준 금액.<br>원화 기준 저축 금액과 합산하여 프로그램이 구동됨. 미입력 시 기본값은 0.0임. |
| `--print-report` | flag | 보고서 출력 모드.<br>설정시 보고서를 파일 뿐 아니라 stdout으로도 출력. |
| `REF_REPORT_PATH` | arg | 분산투자 계산의 기준 JSON 파일 경로.<br>포트폴리오 또는 main.py의 출력파일을 의미. |
| `OUTPUT_REPORT_PATH` (optional) | arg | 분산투자 계산의 출력 JSON 파일 경로.<br>제공되지 않을 경우 main.py는 분산투자 계산 보고서 출력 모드로만 동작 가능. |

보다 간략한 도움말은 `$ (venv) python3 main.py --help`을 입력해도 볼 수 있습니다.

#### 활용 예시
최초 포트폴리오 설정파일이 `initial_portfolio.json`으로 저장돼 있고, 저금할 금액이 1,000,000원인 경우 아래와 같이 첫 번째 투자주기에 대한 출력 보고서를 `result_1st_period.json`이라는 파일로 받을 수 있습니다.

`$ (vevn) python3 main.py --saving-in-krw=1000000 initial_portfolio.json result_1st_period.json`

### 분산투자 결과 JSON의 stock 요소
분산투자 결과 JSON 파일을 생성 시 포트폴리오 JSON 파일을 복제 후 각 상품(stock)의 요소를 수정하거나 추가적인 요소를 삽입하는 방식으로 동작하므로 분산투자 결과 JSON 파일에는 포트폴리오 JSON 파일의 요소가 모두 포함되고 아래의 요소들이 추가적으로 포함된다.

| 항목 | 설명 |
|------|------|
| `"appraisement"` | 해당 상품의 평가액(보유수량 * 단가)의 달러 환산 값 |
| `"need2investCA"` | CA 방식으로 계산한 투자필요량.<br>"저축액 * 투자비중" 값으로 결정. |
| `"need2investVA"` | VA 방식으로 계산한 투자필요량.<br>기존 `"cumSumCaInvested"` 값에 `"need2investCA"` 값을 더한 것에서 `"appraisement"` 값을 뺀 것으로 결정. |
| `"need2invest"` | 최종 투자필요량.<br>포트폴리오 파일에 지정된 투자전략에 따라 CA면 `"need2investCA"` 값으로, VA면 `"need2investVA"` 값으로 결정. |
| `"need2investInUnits"` | 최종 투자필요 수량.<br>`"need2invest"` 값을 각 상품의 현재 단가로 나눈 값과 가장 가까운 정수 값으로 결정. 이 갯수만큼 매수도를 수행하면 된다. |
| `"cum_inv_deviation"` | 매 투자주기별 이상적 투자필요량에서 실제 투자량을 뺀 값의 누계.<br>상품의 단가가 큰 경우나, VA투자의 경우 각 투자주기별 투자필요량이 저축액보다 큰 경우가 있으므로 오차가 필연적으로 발생한다. 여러 투자주기에 걸쳐 이 값을 최대한 0에 가깞게 유지하도록 관리하여 이상적인 분산투자에 최대한 가깝게 운용할 수 있다. |

### 실투자량 입력
본 프로그램으로 상품별 투자필요 수량을 계산한다고 해도 실제 매수도가 어떻게 이뤄지는지는 별개이다. 특히 VA 방식의 경우 각 투자주기별 저축액보다 더 많은 금액을 투자해야 할 수 있어 투자필요 수량만큼 매수를 수행하는 것이 실질적으로 불가능할 수 있다. 따라서 본 프로그램에서는 실제 투자수량을 별도로 추적하여 `"holdings"` 항목에 반영한다. 이때, KIS stockgroup 이외의 stockgroup의 경우 API를 통해 보유수량을 알아낼 수 없어 JSON 파일을 통해 수동으로 실제 투자수량을 입력해 주어야 한다. KIS stockgroup은 현 보유수량을 API를 통해 알아낼 수 있으므로 아래의 작업이 필요치 않다.
실투자수량 입력 방법은 JSON 파일의 각 상품(stock) 항목에 `"actualInvestedInUnits"` 항목을 투자함으로써 이뤄진다. 예를 들어, BTC상품에 대한 분산투자 결과 JSON 파일(`output1.json`)이 아래와 같이 주어졌다고 하자.

```
"BTC": 
{
	"weight": 0.1,
	"market": "OTHER",
	"holdings": 0.02,
	"currency": "USD",
	"descr": "Bitcoin",
	"price": 26227.0,
	"priceROK": 26760.531309297912,
	"kimchi": 1.0203428264497623,
	"appraisement": 524.54,
	"need2investCA": 75.90132827324479,
	"cumSumCaInvested": 1910.8159392789375,
	"need2invest": 1386.2759392789376,
	"need2investVA": 1386.2759392789376,
	"need2investInUnits": 0.05285682461886367,
	"cum_inv_deviation": 1310.3746110056927
}
```

`"need2investInUnits"` 값에서 알 수 있듯, 이상적으로는 0.05285682461886367 BTC를 매수해야 할 것이나, 모종의 이유로 0.05 비트코인만 매수했을 때는 JSON파일의 해당 상품 항목에 아래와 같이 `"actualInvestedInUnits"` 항목을 추가한다.

```
"BTC": {
	...
	"need2investInUnits": 0.05285682461886367,
	"actualInvestedInUnits": 0.05,
	"cum_inv_deviation": 1310.3746110056927
}
```

[활용](#활용) 항목에서 언급한 바 있듯이 이전 투자주기의 분산투자 결과 JSON 파일은 다음 투자주기의 입력 JSON 파일이 된다. 이때 본 프로그램은 입력 JSON 파일의 어떤 상품에 `"actualInvestedInUnits"` 항목이 있다면 이를 실제 투자된 수량으로 보고 `"holdings"`에 합산하는 작업을 수행한다.

구체적으로 `$ (venv) main.py --saving-in-krw=1000000 output1.json output2.json`을 수행하고 `output2.json`의 BTC 항목을 보면 아래와 같이 나타나는데, 이를 `"actualInvestedInUnits"` 항목을 수동으로 추가한 `output1.json`의 BTC 항목과 비교해보면 아래와 같다. `output1.json`에서 `"actualInvestedInUnits"` 항목으로 0.05를 매수했다는 것이 `output2.json`에 반영되어 `"holdings"` 항목이 0.02에서 0.07로 변화했음을 확인할 수 있다.

| `output1.json` | `output2.json` |
|----------------|----------------|
| "BTC":<br>{<br>&emsp;&emsp;...<br>&emsp;&emsp;"holdings": 0.02,<br>&emsp;&emsp;...<br>&emsp;&emsp;"actualInvestedInUnits": 0.05,<br>&emsp;&emsp;...<br>} | "BTC":<br>{<br>&emsp;&emsp;...<br>&emsp;&emsp;"holdings": 0.07,<br>&emsp;&emsp;...<br>} |

### 부가 기능: 분산투자 보고서 출력
프로그램의 부가 기능으로 입력 혹은 계산된 분산투자 결과 JSON 파일을 명령창으로 출력할 수 있다. 이는 프로그램 실행 시 `--print-report` flag를 붙임으로써 활성화된다.

#### 단일 분산투자 JSON 파일 출력
예시 구문
```
$ (venv) main.py --print-report path/to/report.json
```
출력결과 예시
```
Strategy: VA
Total Appraisement: 11897.74
+--------+----------+------------+--------------+------------------+-------------+--------------------+--------------+------------+-------------------+
| stock  | priceUsd |  holdings  | appraisement | cumSumCaInvested | need2invest | need2investInUnits | targetweight | cur_weight | cum_inv_deviation |
+--------+----------+------------+--------------+------------------+-------------+--------------------+--------------+------------+-------------------+
| 069500 |  25.51   |     80     |   2040.80    |     2040.80      |    0.00     |         0          |     0.25     |    0.17    |       0.00        |
| VOO    |  385.87  |     17     |   6559.79    |     6559.79      |    0.00     |         0          |     0.25     |    0.55    |       0.00        |
| BTC    | 27193.00 | 0.02000000 |    543.86    |     1755.63      |   1211.77   |     0.04456182     |     0.1      |    0.05    |       0.00        |
| ETH    | 1844.13  | 0.20000000 |    368.83    |     1755.63      |   1386.80   |     0.75200959     |     0.1      |    0.03    |       0.00        |
| GLD    |  62.88   |     10     |    628.83    |      377.81      |   -251.02   |         -4         |     0.1      |    0.05    |       0.00        |
| KRW    |   0.00   |  1000000   |    755.63    |      755.63      |    0.00     |         0          |     0.1      |    0.06    |       0.00        |
| USD    |    1     |    1000    |   1000.00    |     1000.00      |    0.00     |         0          |     0.1      |    0.08    |       0.00        |
+--------+----------+------------+--------------+------------------+-------------+--------------------+--------------+------------+-------------------+
``` 

#### 분산투자 계산 후 이전(reference) / 이후(derived) 보고서 출력
예시 구문
```
$ (venv) main.py --print-report --saving-in-krw=1000 reference_report.json derived_report.json
```

출력결과 예시
```
Reference Report
----------------------------------------
Strategy: VA
Total Appraisement: 11897.74
+--------+----------+------------+--------------+------------------+-------------+--------------------+--------------+------------+-------------------+
| stock  | priceUsd |  holdings  | appraisement | cumSumCaInvested | need2invest | need2investInUnits | targetweight | cur_weight | cum_inv_deviation |
+--------+----------+------------+--------------+------------------+-------------+--------------------+--------------+------------+-------------------+
| 069500 |  25.51   |     80     |   2040.80    |     2040.80      |    0.00     |         0          |     0.25     |    0.17    |       0.00        |
| VOO    |  385.87  |     17     |   6559.79    |     6559.79      |    0.00     |         0          |     0.25     |    0.55    |       0.00        |
| BTC    | 27193.00 | 0.02000000 |    543.86    |     1755.63      |   1211.77   |     0.04456182     |     0.1      |    0.05    |       0.00        |
| ETH    | 1844.13  | 0.20000000 |    368.83    |     1755.63      |   1386.80   |     0.75200959     |     0.1      |    0.03    |       0.00        |
| GLD    |  62.88   |     10     |    628.83    |      377.81      |   -251.02   |         -4         |     0.1      |    0.05    |       0.00        |
| KRW    |   0.00   |  1000000   |    755.63    |      755.63      |    0.00     |         0          |     0.1      |    0.06    |       0.00        |
| USD    |    1     |    1000    |   1000.00    |     1000.00      |    0.00     |         0          |     0.1      |    0.08    |       0.00        |
+--------+----------+------------+--------------+------------------+-------------+--------------------+--------------+------------+-------------------+

Derived Report
----------------------------------------
Strategy: VA
Total Appraisement: 11897.74
+--------+----------+------------+--------------+------------------+-------------+--------------------+--------------+------------+-------------------+
| stock  | priceUsd |  holdings  | appraisement | cumSumCaInvested | need2invest | need2investInUnits | targetweight | cur_weight | cum_inv_deviation |
+--------+----------+------------+--------------+------------------+-------------+--------------------+--------------+------------+-------------------+
| 069500 |  25.51   |     80     |   2040.80    |     2040.80      |    0.00     |         0          |     0.25     |    0.17    |       0.00        |
| VOO    |  385.87  |     17     |   6559.79    |     6559.79      |    0.00     |         0          |     0.25     |    0.55    |       0.00        |
| BTC    | 27193.00 | 0.02000000 |    543.86    |     1755.63      |   1211.77   |     0.04456182     |     0.1      |    0.05    |      1211.77      |
| ETH    | 1844.13  | 0.20000000 |    368.83    |     1755.63      |   1386.80   |     0.75200959     |     0.1      |    0.03    |      1386.80      |
| GLD    |  62.88   |     10     |    628.83    |      377.81      |   -251.02   |         -4         |     0.1      |    0.05    |      -251.02      |
| KRW    |   0.00   |  1000000   |    755.63    |      755.63      |    0.00     |         0          |     0.1      |    0.06    |       0.00        |
| USD    |    1     |    1000    |   1000.00    |     1000.00      |    0.00     |         0          |     0.1      |    0.08    |       0.00        |
+--------+----------+------------+--------------+------------------+-------------+--------------------+--------------+------------+-------------------+
```