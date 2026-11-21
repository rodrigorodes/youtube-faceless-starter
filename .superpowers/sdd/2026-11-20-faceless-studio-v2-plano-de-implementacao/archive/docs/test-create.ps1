$body = @{ topic = "Como a inteligencia artificial funciona?"; format = "short"; duration_seconds = 20; style = "documentary" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/videos" -Method Post -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 5
