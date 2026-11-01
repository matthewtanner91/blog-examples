import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.ArchRule;
import com.tngtech.archunit.library.freeze.FreezingArchRule;
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

public class ArchitectureCheck {
    public static void main(String[] args) {
        JavaClasses classes = new ClassFileImporter().importPackages("example");
        ArchRule rule = noClasses()
            .that().resideInAPackage("example.domain..")
            .should().dependOnClassesThat()
            .resideInAPackage("example.persistence..")
            .because("domain code must not bind to persistence implementations");
        if (args.length > 1 && args[1].equals("renamed")) {
            rule = rule.as("domain must stay independent of persistence");
        }
        if (args.length > 0 && args[0].equals("frozen")) {
            rule = FreezingArchRule.freeze(rule);
        }
        rule.check(classes);
        System.out.println("PASS");
    }
}
