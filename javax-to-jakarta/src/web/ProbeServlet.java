package demo;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

public final class ProbeServlet extends HttpServlet {
    @Override
    protected void doGet(HttpServletRequest request, HttpServletResponse response)
            throws IOException {
        response.setContentType("text/plain;charset=UTF-8");
        Properties settings = new Properties();
        try (InputStream stream = getClass().getResourceAsStream("/probe.properties")) {
            if (stream == null) throw new IOException("Missing probe.properties");
            settings.load(stream);
        }
        String api = settings.getProperty("request.api");
        try {
            if (!Class.forName(api).isInstance(request)) {
                response.setStatus(500);
                response.getWriter().print("REFLECTION_WRONG_TYPE=" + api);
                return;
            }
        } catch (ClassNotFoundException e) {
            response.setStatus(500);
            response.getWriter().print("REFLECTION_MISSING=" + api);
            return;
        }
        try {
            response.getWriter().print(RequestLabel.describe(request)
                + ";initializer=" + getServletContext().getAttribute("initializer"));
        } catch (LinkageError e) {
            response.setStatus(500);
            response.getWriter().print("LINKAGE_ERROR=" + e.getClass().getSimpleName());
        }
    }
}
