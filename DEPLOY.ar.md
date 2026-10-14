# دليل النشر — AgentCraft Engineering Lab

## 1. المتطلبات
- Linux (Ubuntu 22.04+)
- Docker Engine 24+ + Docker Compose v2
- Nginx Proxy Manager (مُثبّت مسبقاً)
- 4 GB RAM كحد أدنى

## 2. التثبيت السريع
```bash
git clone https://github.com/mayakilzy/AgentCraft-Engineering-Lab.git
cd AgentCraft-Engineering-Lab
docker network create agentcraft-proxy
cp .env.production.example .env
nano .env  # استبدل كل CHANGE_ME_* بكلمات مرور قوية
./deploy.sh up
./deploy.sh status
```

## 3. إعداد NPM
1. أضف شبكة `agentcraft-proxy` إلى compose الخاص بـ NPM
2. في واجهة NPM: Add Proxy Host → `web:80`, Websockets ✓, SSL (Let's Encrypt)
3. تحقق: `curl -I https://your-domain.example.com`

## 4. النسخ الاحتياطي
```bash
./deploy.sh backup
# استعادة PostgreSQL:
cat backups/postgres-*.sql | docker compose exec -T postgres psql -U agentcraft agentcraft
```

## 5. استكشاف الأخطاء
```bash
./deploy.sh logs
docker compose ps
```

## 6. ما لم يُختبر
هذا الدليل أُعدّ بدون Docker. التالي CONFIG READY لكن ليس RUNTIME VERIFIED:
- بناء صور Docker
- تشغيل خدمات Compose
- إنشاء NPM Proxy Host
- شهادات TLS

بعد النشر: `./deploy.sh test-runner`
