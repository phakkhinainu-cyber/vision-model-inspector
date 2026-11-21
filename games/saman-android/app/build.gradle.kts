import java.util.Properties

plugins {
    id("com.android.application")
}

// คัดลอกเกม (ไฟล์ HTML ไฟล์เดียว) เข้าแอปตอน build — แก้เกมที่ ../saman-runner.html ที่เดียวพอ
abstract class CopyGameTask : DefaultTask() {
    @get:InputFile abstract val source: RegularFileProperty
    @get:OutputDirectory abstract val outputDir: DirectoryProperty
    @TaskAction fun run() {
        val out = outputDir.get().asFile
        out.mkdirs()
        source.get().asFile.copyTo(File(out, "index.html"), overwrite = true)
    }
}
val copyGame = tasks.register<CopyGameTask>("copyGame") {
    source.set(rootProject.layout.projectDirectory.file("../saman-runner.html"))
}

// กุญแจเซ็นแอปสำหรับ Play Store: อ่านจาก keystore.properties (ไม่อยู่ใน git)
val keyProps = Properties().apply {
    val f = rootProject.file("keystore.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

android {
    namespace = "com.samanrunner.game"
    compileSdk = 36

    defaultConfig {
        // ⚠️ เปลี่ยนเป็นชื่อแพ็กเกจของคุณเองก่อนอัปโหลดครั้งแรก (แก้ทีหลังไม่ได้)
        applicationId = "com.samanrunner.game"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
    }

    signingConfigs {
        if (keyProps.getProperty("storeFile") != null) {
            create("upload") {
                storeFile = rootProject.file(keyProps.getProperty("storeFile"))
                storePassword = keyProps.getProperty("storePassword")
                keyAlias = keyProps.getProperty("keyAlias")
                keyPassword = keyProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfigs.findByName("upload")?.let { signingConfig = it }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(copyGame, CopyGameTask::outputDir)
    }
}
