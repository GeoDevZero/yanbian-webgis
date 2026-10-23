
// 1. 初始化地图
// 建地图 
const map = L.map('map').setView([42.90, 129.51], 9);

// 加底图（高德，GCJ-02，和 DataV 下载的边界数据能对上）
L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', {
  subdomains: '1234',
  maxZoom: 18,
  attribution: '&copy; 高德地图'
}).addTo(map);
// 专门放"AI 画的东西"的图层组（clearLayers 时不会误删底图上的县界）
let actionLayer = L.featureGroup().addTo(map);

// 2. 功能函数
// 2.1 读取并渲染地图数据
// 读取同目录下的 GeoJSON 文件
// 用 async/await 读取 GeoJSON
async function loadMap() {
  try {
    console.log('开始读取 GeoJSON...');

    const res = await fetch('./yanbian.geojson');   // 等：网络请求
    const data = await res.json();                  // 等：解析 JSON

    console.log('读到了 ' + data.features.length + ' 个要素');

    const layer = L.geoJSON(data, {
      style: { color: '#c00', weight: 1.5, fillColor: '#f66', fillOpacity: 0.2 },
      // onEachFeature: (f, lyr) => lyr.bindPopup(f.properties.name || '未命名')
      onEachFeature: (f, lyr) => {
        // 点击弹窗（D1 原有）
        lyr.bindPopup(f.properties.name || '未命名');

        // 点击后显示到侧栏（D4 Part D 新增）
        lyr.on('click', async () => {
          const name = f.properties.name || '未命名';
          document.getElementById('feature-info').textContent = `你选中了：${name}`;
          try {
            const res = await fetch(
              'http://localhost:8001/api/chat?q=' + encodeURIComponent(`用一句话介绍${name}`)
            );
            const data = await res.json();
            document.getElementById('feature-info').textContent =
              `你选中了：${name}\n\n${data.回答}`;
          } catch (err) {
            document.getElementById('feature-info').textContent = `你选中了：${name}（介绍生成失败）`;
          }
        });
      }


    }).addTo(map);

    map.fitBounds(layer.getBounds());
  } catch (err) {
    // 出错时直接显示在页面上，而不是悄悄白屏
    document.body.innerHTML =
      '<pre style="color:red;padding:20px">读取 GeoJSON 失败：' + err + '</pre>';
  }
}

loadMap();

// 2.2 读取后端统计数据
async function loadStats() {
  try {
    const res = await fetch('http://localhost:8001/api/stats');
    const data = await res.json();

    // ① 显示总数
    document.getElementById('stat-summary').textContent =
      `延边州共 ${data.要素总数} 个县市`;

    // ② 循环渲染列表
    const ul = document.getElementById('county-list');
    ul.innerHTML = '';   // 先清空

    for (const name of data.县市列表) {
      const li = document.createElement('li');
      li.textContent = name;
      ul.appendChild(li);
    }
  } catch (err) {
    document.getElementById('stat-summary').textContent = '加载失败：' + err;
  }
}

loadStats();   // 页面加载时调用

// 2.3 把后端返回的绘图指令画到地图上
function applyMapActions(actions) {
  actionLayer.clearLayers();            // 先清掉上一次画的
  if (!actions || actions.length === 0) return;

  for (const a of actions) {

    if (a.类型 === 'circle') {
      // ⚠️ 顺序：GeoJSON 是 [经度, 纬度]，Leaflet 要 [纬度, 经度]
      const [lng, lat] = a.经纬度;

      L.circle([lat, lng], {
        radius: a.半径公里 * 1000,          // Leaflet 的 radius 单位是【米】
        color: '#0066cc',
        weight: 2,
        fillColor: '#3388ff',
        fillOpacity: 0.15,
      }).addTo(actionLayer).bindPopup(a.标注 || '');

      // 圆心加个小点，看得更清楚
      L.circleMarker([lat, lng], { radius: 4, color: '#0066cc', fillOpacity: 1 })
        .addTo(actionLayer)
        .bindPopup(a.标注 || '');

    } else if (a.类型 === 'line') {
      // a.坐标 是 [[经度,纬度], [经度,纬度]]，要转成 [[纬度,经度], ...]
      const latlngs = a.坐标.map(([lng, lat]) => [lat, lng]);

      L.polyline(latlngs, {
        color: '#0066cc',
        weight: 3,
        dashArray: '6 4',                   // 虚线
      }).addTo(actionLayer).bindPopup(a.标注 || '');

      // 两端加标记
      latlngs.forEach((p) => {
        L.circleMarker(p, { radius: 4, color: '#0066cc', fillOpacity: 1 })
          .addTo(actionLayer);
      });
    }
  }

  // 把视野移到刚画的东西上
  const b = actionLayer.getBounds();
  if (b.isValid()) map.fitBounds(b.pad(0.3));
}


async function sendChat() {
  const input = document.getElementById('chat-input');
  const q = input.value.trim();

  if (!q) return;                    // 空的不发

  const log = document.getElementById('chat-log');

  // ① 先把"我问的"显示出来
  log.innerHTML += `<div class="msg me">${q}</div>`;
  input.value = '';                  // 清空输入框

  // ② 显示"思考中"
  const loadingId = 'loading-' + Date.now();
  log.innerHTML += `<div class="msg ai" id="${loadingId}">思考中…</div>`;

  try {
    // 1) 拼出请求地址：注意要用 encodeURIComponent 包住 q！
    const url = 'http://localhost:8001/api/chat?q=' + encodeURIComponent(q);
    const res = await fetch(url);
    const data = await res.json();
    // 4) 把 loading 替换成回答：
    document.getElementById(loadingId).textContent = data.回答 || '（无回答）';
    try { applyMapActions(data.地图动作); }
    catch (e) { console.error('绘图失败（不影响回答）:', e); }

  } catch (err) {
    document.getElementById(loadingId).textContent = '出错了：' + err;
  }
}

// 绑定事件：点按钮 + 回车
document.getElementById('chat-send').addEventListener('click', sendChat);
document.getElementById('chat-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendChat();
});


