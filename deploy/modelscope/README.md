---
license: mit
---

# 出行建议官 · Travel Advisor

输入 **日期 + 城市 + 出行模式**，返回一份可解释、能直接照做的出行建议。

- 规则引擎负责事实：气候常年值、法定节假日与调休、二十四节气、通勤高峰、旅游人流
- 可选接入和风天气预报与 DeepSeek 润色；未配置时自动使用纯规则模式
- 支持通勤、旅游两种模式，新增模式只需加一个 `Mode` 子类
- 源码与完整文档：https://github.com/aaa1173188435/travel-advisor

## 环境变量

在**创空间设置 → 环境变量**中添加（运行时注入，不要写进代码）：

| 名称 | 说明 |
| --- | --- |
| `TRAVEL_ADVISOR_WEATHER_KEY` | 和风天气 Key（可选） |
| `TRAVEL_ADVISOR_WEATHER_BASE_URL` | 和风 API Host（可选） |
| `DEEPSEEK_API_KEY` | DeepSeek Key（可选） |

不配置任何变量也能使用，此时天气为气候常年值估算、不调用大模型。
