package demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import org.apache.catalina.Context;
import org.apache.catalina.startup.Tomcat;

public final class ProbeRunner {
    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("war status body");
        Tomcat tomcat = new Tomcat();
        Path work = Path.of("work").toAbsolutePath();
        Files.createDirectories(work);
        Path base = Files.createTempDirectory(work, "tomcat-probe-");
        System.out.println("TOMCAT_BASE=" + base);
        tomcat.setBaseDir(base.toString());
        Path appBase = Files.createDirectories(base.resolve("webapps"));
        tomcat.getHost().setAppBase(appBase.toString());
        // This fixture has no JSP/static pages; retain its own web.xml and SCI processing.
        tomcat.setAddDefaultWebXmlToWebapp(false);
        tomcat.setPort(0);
        tomcat.getConnector().setProperty("address", "127.0.0.1");
        Path war = Path.of(args[0]).toAbsolutePath();
        if (!Files.isRegularFile(war)) throw new IllegalArgumentException("Missing WAR: " + war);
        Context context = tomcat.addWebapp("", war.toString());
        try {
            tomcat.start();
            if (!context.getState().isAvailable() || context.findChild("jsp") != null) {
                throw new AssertionError("CONTEXT_CONFIGURATION_FAILED");
            }
            int port = tomcat.getConnector().getLocalPort();
            HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + "/probe?name=pilot"))
                .timeout(Duration.ofSeconds(10)).GET().build();
            HttpResponse<String> response = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5)).build()
                .send(request, HttpResponse.BodyHandlers.ofString());
            System.out.println("OBSERVED_STATUS=" + response.statusCode());
            System.out.println("OBSERVED_BODY=" + response.body());
            if (response.statusCode() != Integer.parseInt(args[1])
                    || !Arrays.asList(args[2].split("\\|", -1)).contains(response.body())) {
                throw new AssertionError("PROBE_FAILED");
            }
            System.out.println("PROBE_PASS");
        } finally {
            try {
                tomcat.stop();
            } finally {
                tomcat.destroy();
            }
        }
    }
}
