package demo;

import javax.servlet.ServletRequest;
import javax.sql.DataSource;

public final class RequestLabel {
    private RequestLabel() {}
    public static String describe(ServletRequest request) {
        return "name=" + request.getParameter("name")
            + ";sql=" + DataSource.class.getName();
    }
}
