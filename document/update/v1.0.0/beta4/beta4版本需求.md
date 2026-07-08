# 需求

## 需求说明

这是一个较大改动的版本，可能需要你自己对这个python版本的代码进行分析和调试

开始工作之前，请你阅读document\Agent开发规范.md
我需要你解决和实现的内容是

0. 当前力场预览仍然不符合需求，请不要只修 F1-F4。F1-F4 只是显示层问题，比如 vertexColors 显示、更新频率、采样密度、退出恢复材质，但真正的问题是：整个 Mesh 都被热力图覆盖了，没有 Cell 覆盖的区域也被着色。

我需要的不是“全模型热力图皮肤”，而是“由 Cell 压力驱动的局部压力场重建”。

正确数据流必须是：

Simulated Pressure / Real Pressure
    ↓
cell.pressure
    ↓
Wendland Reconstruction
    ↓
vertexPressure + vertexConfidence
    ↓
只在有 Cell 覆盖的 Mesh 区域显示热力图

禁止：

time / sine wave / vertex position
    ↓
直接生成 Mesh 颜色

---

## 1. 增加 vertexConfidence / coverage mask

每个 vertex 不仅要计算 pressure，还要计算 confidence。

```cpp
pressureSum = 0;
weightSum = 0;

for each cell:
    d = distance(vertex.position, cell.position);
    r = d / query_radius;

    if (r <= 1.0)
    {
        w = pow(1.0 - r, 4.0) * (4.0 * r + 1.0);

        pressureSum += cell.pressure * w;
        weightSum += w;
    }

if (weightSum > epsilon)
{
    vertexPressure = pressureSum / weightSum;
    vertexConfidence = clamp(weightSum, 0.0, 1.0);
}
else
{
    vertexPressure = 0.0;
    vertexConfidence = 0.0;
}



阅读完该文档，D:\workshop\3D-\document\update\v1.0.0\beta3\问题清单.md   里面的问题是我解答的 如果有新问题请继续补充  对我进行提问确认问题