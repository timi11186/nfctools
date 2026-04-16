# NFC烧录系统

这是一个用于NFC卡烧录的系统，可以将指定的URL烧录到NFC卡中。现在系统支持为每个NFC卡生成唯一的用户ID，并将数据存储到数据库中。

## 系统结构

- `backend`：后端API服务
- `client`：前端GUI应用
- `data`：数据存储目录
- `assets`：资源文件

## 新功能

- 自动为每张NFC卡生成随机用户ID，并附加到URL中
- 记录NFC卡ID和用户ID到数据库
- 支持数据导出，方便与网站项目集成

## 安装指南 (新电脑设置)

1. 安装Python 3.8或更高版本

2. 克隆本仓库到本地

3. 安装依赖包：
   ```bash
   pip install -r requirements.txt
   ```

4. 初始化数据库：
   ```bash
   python init_db.py
   ```

5. 如果你已有旧版本的数据库，运行迁移脚本以更新表结构：
   ```bash
   python migrations.py
   ```

## 运行项目

1. 启动应用：
   ```bash
   python run.py
   ```

2. 登录系统：
   - 管理员账号：admin
   - 默认密码：admin123

## 硬件要求

- 支持的读卡器：ACR122U或兼容的USB NFC读卡器
- 支持的NFC卡：NTAG213, FM08

## 故障排除

### 读卡器未检测到

- 确保已安装读卡器驱动
- Windows系统：可能需要安装[ACS驱动](https://www.acs.com.hk/en/driver/3/acr122u-usb-nfc-reader/)
- 确认读卡器已正确连接

### 数据库问题

- 如果数据库损坏或需要重置，可删除`data/nfc_system.db`文件，然后重新运行`init_db.py`

## 数据导出

系统将NFC卡ID和用户ID存储在数据库中，你可以通过以下方式导出数据：

1. 使用SQLite浏览器工具查看和导出数据
2. 开发自定义导出脚本，根据需要格式化数据

## 扩展集成

可以通过以下方式将NFC数据与网站集成：

1. 将`data/nfc_system.db`数据库文件复制到网站项目中
2. 编写导入脚本，将NFC数据导入到网站数据库
3. 在网站应用中添加处理URL参数`uid`的逻辑，与用户记录关联 